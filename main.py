#!/usr/bin/env python
# encoding: utf-8

import ffmpeg
import time
import hashlib
import json
import urllib
import os
import sys
import logging

logging.getLogger().setLevel(logging.INFO)

from flask import Flask, abort, request, jsonify, send_file

_allowed_params = ['start', 'end', 'q', 'height', 'width', 'fast'] # Allowed parameters in the URL request
SOURCE_BUCKET_NAME = 'LOL'
DESTINATION_BUCKET_NAME = 'LOL'
LOCAL_DESTINATION_PATH = './outputs'
FFMPEG_BINARY_PATH = './ffmpeg_static_builds/mac/ffmpeg'

if os.environ.get('GCP_PROJECT', None) is not None:
	FFMPEG_BINARY_PATH = './ffmpeg_static_builds/amd64/ffmpeg'
	LOCAL_DESTINATION_PATH = '/tmp'


def generate_hash(message):
	"Returns an MD5 hash given a message."
	hashmd5 = hashlib.md5(str(message).encode('utf-8')).hexdigest()
	return hashmd5

def request_signed_url(filename):
	"Request and return a protected signed URL from the source bucket."

	url = '{}/{}'.format('http://storage.googleapis.com/test_videos_mp4', urllib.parse.quote(filename))
	return url

def check_in_datastore(md5_hash):
	"Check if this unique query is repeated in the datastore."
	return md5_hash

def insert_to_datastore(md5_hash, location):
	"Add this unique query to the datastore."
	return (md5_hash, location)

def upload_to_storage_and_return_url(filename):
	"Upload the processed file to cloud storage and return the path."
	return filename

def round_to_nearest_even(number):
	number = int(number)

	if number % 2 == 1: # Odd heights are not allowed in codec spec
		number += 1

	return number




def trim(request):
	if request.path == '/favicon.ico': abort(404) # Ignore browser requests for favicon

	request.path = request.path.strip('/').split('/')
	_operation = request.path[0]
	_source_params = request.path[1]
	_source_file = request.path[2]
	_time = int(time.time())
	_params = dict()
	_hash = None

	# Extract parameters from URL field
	for param in _source_params.split(','):
		try:
			_split = param.split(':')
			_key = _split[0]
			_value = _split[1] if len(_split) > 1 else None

			if _key in _allowed_params:
				_params[_key] = _value
			else: abort(400)
		except: abort(400)

	## Generate hash
	_hash = generate_hash("{}:{}".format(json.dumps(_params, sort_keys=True), _source_file))

	## Create args for ffmpeg.input
	_input_kwargs = dict()
	_input_kwargs['multiple_requests'] = '1' # Reuse tcp connections

	if _operation == 'thumbnail' and 'start' in _params and '%' in _params['start']:
		probe = ffmpeg.probe(request_signed_url(_source_file))
		video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
		_params['start'] = (float(_params['start'].strip('%')) / 100) * float(video_stream['duration'])

	if 'start' in _params:
		_input_kwargs['ss'] = float(_params['start'])

	if 'end' in _params:
		_input_kwargs['t'] = float(_params['end']) - float(_params['start'])

	## FFprobe (requires another complete moov atom handshake, slow)
	#probe = ffmpeg.probe(request_signed_url(_source_file))
	#video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
	#width = int(video_stream['width'])
	#height = int(video_stream['height'])

	## Run FFMPEG
	#watermark = ffmpeg.input('./watermark.png')

	job = ffmpeg.input(request_signed_url(_source_file), **_input_kwargs)
	#job = ffmpeg.filter(job, 'fps', fps=25, round='up')
	#job = ffmpeg.drawbox(job, 50, 50, 120, 120, color='red', thickness=5)
	#job = ffmpeg.overlay(job, watermark)

	kwargs = dict()
	kwargs['movflags'] = '+faststart' # moov atom in front
	kwargs['hide_banner'] = None # hide ffmpeg banner from logs
	kwargs['nostdin'] = None # disable interactive mode
	kwargs['loglevel'] = 'debug' # more detailed logs from ffmpeg

	if _operation == 'thumbnail':
		kwargs['vframes'] = '1'

	if 'height' in _params:
		# Set fixed heigh & scale width to closest even number
		kwargs['vf'] = "scale=-2:'min({},ih)'".format(round_to_nearest_even(_params['height']))

	if 'width' in _params:
		kwargs['vf'] = "scale='min({},iw)':-2".format(round_to_nearest_even(_params['width']))

	if 'fast' in _params and ('height' in _params or 'width' in _params):
		abort(400)

	if 'fast' in _params:
		kwargs['c'] = 'copy'


	job = ffmpeg.output(job, '{}/{}_{}.{}'.format(LOCAL_DESTINATION_PATH, _time, _hash, 'mp4' if _operation == 'trim' else 'jpg'), **kwargs)

	try:
		out, err = ffmpeg.run(job, cmd=FFMPEG_BINARY_PATH, capture_stderr=True, capture_stdout=True)

		# read source metadata from out?
		#logging.info(out.decode('utf-8').replace('\n', ' '))
		#logging.error(err.decode('utf-8').replace('\n', ' '))

	except ffmpeg.Error as e:
		logging.error(e.stderr.decode().replace('\n', ' '))
		logging.error(e.stderr)
		logging.error(e)

		#print(e.stderr.decode(), file=sys.stderr)

	logging.info({
		'params': _source_params,
		'js_params': _params,
		'ffmpeg_input_args': _input_kwargs,
		'ffmpeg_output_args': kwargs,
		'ffmpeg_command': " ".join(ffmpeg.compile(job)),
		'source_file': _source_file,
		'hash': _hash,
		#'video_stream': video_stream
	})


	return send_file('{}/{}_{}.{}'.format(LOCAL_DESTINATION_PATH, _time, _hash, 'mp4' if _operation == 'trim' else 'jpg'))

	#return jsonify({
	#	'params': _source_params,
	#	'js_params': _params,
	#	'ffmpeg_input_args': _input_kwargs,
	#'ffmpeg_output_args': kwargs,
	#	'ffmpeg_command': " ".join(ffmpeg.compile(job)),
	#	'source_file': _source_file,
	#	'hash': _hash,
	#	#'video_stream': video_stream
	#})



# https://storage.googleapis.com/test_videos_mp4/%5B60fps%5D%205%20minutes%20timer%20with%20milliseconds-CW7-nFObkpw.mp4
# https://storage.googleapis.com/test_videos_mp4/bigbuckbunny.mp4

# ffmpeg -y -ss 00:00:05.000 -i "https://storage.googleapis.com/test_videos_mp4/bigbuckbunny.mp4" -t 00:00:05.000 -c:a copy -c:v copy output.mp4
# ffmpeg -y -ss 00:00:05.000 -i "http://storage.googleapis.com/test_videos_mp4/bigbuckbunny.mp4" -t 00:00:05.000 -c:a copy -c:v copy output.mp4

# Return 302 directly if file hash already exists in storage
# Return 302 after finishing uploading and processing (to avoid Lambda and GCF response size limits)
# Combine clips
# Watermarking
# Signed URL generation for private source bucket (and for output as well)
# moov_atom
# configuration file format
# GCP Functions / AWS Lambda
# Include ffmpeg static build?
# -c copy if 1) mp4 2) only trim and 3) acceptable to have end freeze

# Things to test
#	moov-atom at the back source file
#	MOVs, AVIs, WAVs, FLVs
#	Benchmark processing times on various serverless configs
#	Benchmark ffmpeg invocation, download, transcode, upload times
#	Benchmark serverless vs container pricing per clip
#	Benchmark cross region load times (GCP Japan to GCS Taiwan)




if __name__=="__main__":
	app = Flask(__name__)

	@app.route('/', defaults={'path': ''})
	@app.route('/<path:path>')
	def index(path):
	    return trim(request)

	app.run('0.0.0.0', 5000, debug=True)







