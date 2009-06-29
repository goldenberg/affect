#!/usr/bin/env python
# encoding: utf-8
help_message = """%prog WAV_FILENAME LOG_FILENAME [options]
This script parses an Apache web server log for requests for the SESDC
experiment corresponding to a voice recording in a WAV file. The script first
locates a request for the index page within a given time window of the
timestamp in the WAV filename. Then subsequent requests which contain the
client_time and show_param parameters are parsed and an output file with three
columns is created. The columns are

1) the stage name (e.g. slide8366, picRecall, vidRating, ...) 
2) the stage start time in seconds 
3) the stage end time in seconds

A separate file containing stage time durations can be specified via the -d
option. If a duration is specified in this file, that duration will be used
instead of the one specified by the client_time argument. If a classification
file is specified via the -c option, the class number will be included in a
4th column.

Written by Benjamin Goldenberg, June 2009.
"""

import sys
import os
import apachelog
import optparse
import urlparse
import logging
import pdb

from datetime import datetime, time, timedelta

# Format copied and pasted from Apache conf - use raw string + single quotes
apache_format = r'%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\"'
apache_parser = apachelog.parser(apache_format)

logging.basicConfig(level=logging.DEBUG)

def main():
    usage = """ %prog WAV_FILENAME LOG_FILENAME [options] """
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-d", "--delays", dest="delays_filename", help="An optional argument to"
                          " specify a TSV file which contains the delays for each stage.")
    opt_parser.add_option("-c", "--classes", dest="classes_filename", help="An optional argument to specify a TSV file "
                          "which contains classes for each stage.")
    opt_parser.add_option("-s", "--svm", action='store_true', default=False, dest="svm_output", help="Flag to also generate "
                            "an input file suitable for input into Max's pitch, format and energy analyzer. Requires a classes file.")
    opt_parser.add_option("-r", "--ratings", action='store_true', default=False,
                            dest="use_url_ratings", help="Parses the 'rating' URL parameter"
                            " to classify the recordings.")
    opt_parser.add_option("-b", "--binary", action='store_true', default=False,
                            dest='Collapse the rating parameter into two classes (plus neutral)'
                            ' (i.e. group {1,2}, {3}, {4,5})')
    
    options, arguments = opt_parser.parse_args()
    
    wav_filename = arguments[0]
    log_filename = arguments[1]
    out_filename = os.path.splitext(wav_filename)[0] + '.tsv'
    
    log_file = open(log_filename)
    wav_time = parse_wav_timestamp(wav_filename)
    
    if options.delays_filename:
        delays = read_delays_file(options.delays_filename)
    else:
        delays = {}
    
    if options.classes_filename:
        classes = read_classes_file(options.classes_filename)
    else:
        classes = {}
    
    ip_address = find_first_request(wav_time, log_file)
    logging.info("The IP address of interest is %s" % ip_address)
    
    stage_dicts = parse_entire_file(log_file, ip_address, wav_time, delays=delays, classes=classes)
    write_stage_output(stage_dicts, out_filename)
    
    if options.svm_output:
        if not options.classes_filename:
            logging.error("In order to generate a file for pitch, formants and energy analysis, you must also specify classes.")
        else:
            svm_filename = os.path.splitext(wav_filename)[0] + '.svmin'
            write_svm_output(stage_dicts, wav_filename, svm_filename)

def parse_entire_file(log_file, ip_address, wav_time, delays={}, classes={}):
    '''
    Parses the rest of the file and returns a list of dictionaries which each
    represent one stage. Each dictionary has 3 required keys: "name",
    "start_time", "end_time" and an optional key: "class"
    
     Iterates through the log_file, picking up where find_first_request() left
    off and determines whether each line is relevant and parses it to
    determine when stages start and stop.
    '''
    output_dicts = []
    
    last_request = ''
    
    for line in log_file:
        if is_line_relevant(line, ip_address):
            (host, log_time, request, referer, user) = parse_line(line)
            logging.debug("The line is relevant: %s" % line)
            if last_request == '':
                last_request = request
                continue
            else:
                (last_stage, last_time, last_duration) = parse_request(last_request, delays=delays)
                (current_stage, current_time, current_duration) = parse_request(request, delays=delays)
                
                start_time = current_time - last_duration - wav_time
                end_time = current_time - wav_time
                
                stage_dict = { "name" : last_stage, 
                               "start_time" : start_time,
                               "end_time" : end_time }
                
                if last_stage in classes:
                    stage_dict["class"] = classes[last_stage]
                
                output_dicts.append(stage_dict)
                
                last_request = request
    
    # deal with last request, which should be the video recall stage
    # assume that the request is served instantly
    current_stage, current_time, current_duration = parse_request(last_request, delays=delays)
    
    start_time = current_time - wav_time
    end_time = current_time - wav_time + current_duration
    
    fields = [current_stage, format_timedelta(start_time), format_timedelta(end_time)]
    stage_dict = { "name"       : current_stage, 
                   "start_time" : start_time,
                   "end_time"   : end_time }
    if current_stage in classes:
        stage_dict["class"] = classes[current_stage]
    
    output_dicts.append(stage_dict)
    
    return output_dicts

def read_delays_file(filename):
    '''
    Reads a TSV file with two columns: slide name and duration in seconds. 
    Returns a dictionary of timedelta objects keyed by slide names (with no 
    file extensions).
    '''
    
    delays = {}
    
    for line in open(filename):
        fields = line.split('\t')
        delays[fields[0]] = timedelta(seconds=int(fields[1]))
    
    return delays

def read_classes_file(filename):
    '''
    Reads a TSV file with two columns: slide name and duration in seconds. 
    Returns a dictionary of timedelta objects keyed by slide names (with no 
    file extensions).
    '''
    
    classes = {}
    
    for line in open(filename):
        fields = line.split('\t')
        classes[fields[0]] = int(fields[1])
    
    return classes

def find_first_request(wav_time, log_file, window=3000):
    '''
    Finds the first request for http://www.csee.ogi.edu/~zak/sesdc/ within a
    specified number of seconds of the wav_time. log_file should be a file-like
    object, wav_time should be a datetime object and window is the number of
    seconds within which to locate the request.
    
    Returns the IP address the request originated from. Returns None if there was
    no matching request within the time window.
    '''
    time_window = timedelta(seconds=window)
    
    for line in log_file:
        (host, log_time, request, referer, user) = parse_line(line)
        
        if '/~zak/sesdc/index2' in request:
            logging.debug("I found a request to index2.html at time %s" % log_time)
            if abs(log_time - wav_time) <= time_window:
                return host
            elif log_time - wav_time > time_window:
                logging.warning("I found a request to index2.html, but it "
                                "occured at %s which was outside the time window of %s"
                                % (log_time, time_window))    
    logging.error('Could not find a request to index2.html within %i seconds of %s' % (window, wav_time))
    
def is_line_relevant(line, ip):
    '''
    Determines whether a line in the log file is relevant to the current ip.
    '''
    (host, log_time, request, referer, user) = parse_line(line)
    
    if host != ip:
        logging.debug("The hosts don't match. The request host was %s" % host)
        return False
    else:
        url_components = urlparse.urlparse(request.split(' ')[1])
        query_params = urlparse.parse_qs(url_components.query)
        
        return ('client_time' in query_params and 'show_param' in query_params)

def parse_line(line):
    '''
    Returns a tuple with the following items: host, time, request, referer, user
    '''
    
    data = apache_parser.parse(line)
    host = data['%h']
    time = parse_timestamp(data['%t'])
    request = data['%r']
    referer = data['%{Referer}i']
    user = data['%u']
    
    return (host, time, request, referer, user)

def parse_request(request, delays={}, date=None):
    '''
    Returns a tuple:
    
    1) the stage name. e.g. recall, slide7009, rating
    2) the client time as a datetime object. the date portion is a dummy date
    3) the stage duration (from the show_param parameter) as a timedelta object
    
    The datetime object will represent a time on Jan 1, 1990.
    
    >>> parse_log.parse_request("GET /~zak/sesdc/slides/8234.html?client_time=10:1:59:745&show_param=116&show_seq=8366:8635:8563:24004:24003:24006:8774 HTTP/1.1")
    ('8234', datetime.datetime(1900, 1, 1, 10, 1, 59, 745000), datetime.timedelta(0, 116))
    '''
    
    if request.strip() == '':
        logging.error("Trying to parse an empty request.")
        return
    
    logging.debug("The request is: %s" % request)
    url_components = urlparse.urlparse(request.split(' ')[1])
    
    pagename = os.path.splitext(os.path.basename(url_components.path))[0]
    
    if pagename == 'sam1':
        stage_name = 'picRating'
    elif pagename == 'sam2':
        stage_name = 'vidRating'
    elif pagename in ('picRecall', 'videoRecall'):
        stage_name = pagename
    else:
        stage_name = 'slide' + pagename
    
    query_params = urlparse.parse_qs(url_components.query)
    
    client_datetime = datetime.strptime(query_params['client_time'][0], '%H:%M:%S:%f')
    
    if pagename in delays:
        stage_duration = delays[pagename]
    else:
        stage_duration = timedelta(seconds=int(query_params['show_param'][0]))
    
    return stage_name, client_datetime, stage_duration

def write_stage_output(stage_dicts, out_filename):
    '''
    Writes a the stage dictionaries to a file, separated by newlines.
    '''
    f = open(out_filename, 'w')
    
    for stage in stage_dicts:
        fields = [stage['name'], format_timedelta(stage['start_time']), format_timedelta(stage['end_time'])]
        if 'class' in stage:
            fields.append('%+i' % stage['class'])
        
        f.write('%s\n' % '\t'.join(fields))
    
    f.close()

def write_svm_output(stage_dicts, wav_filename, out_filename):
    '''
    Writes an output file suitable for input into Max's pitch, formants and 
    energy analyzer in the following format:
    
    wav_filename    class   start_time  end_time    
    
    Ignores all dicts without a class attribute. Only writes classes that are
    -1 or +1. 0s are ignored.
    '''
    
    f = open(out_filename, 'w')
    
    for stage in stage_dicts:
        if 'class' in stage:
            if stage['class'] == -1:
                the_class = 0
            elif stage['class'] == 1:
                the_class = 1
            
            if stage['class'] != 0:
                f.write('%s\t%i\t%s\t%s\n' % (wav_filename, the_class, format_timedelta(stage['start_time']), 
                                                    format_timedelta(stage['end_time'])))
    
    f.close()

def parse_wav_timestamp(wav_filename):
    '''
    Returns a datetime object extracted from the wav filename. Should 
    correspond to the beginning of the recording.
    
    >>> get_wav_timestamp('2009-05-20_09-49-28_l0_.wav')
    datetime.datetime(2009, 5, 20, 9, 49, 28)
    '''
    basename = os.path.basename(wav_filename)
    format = '%Y-%m-%d_%H-%M-%S_l0_.wav'
    
    return datetime.strptime(basename, format)

def parse_timestamp(timestamp):
    '''
    Parses a timestamp of the form [20/May/2009:10:14:18 -0700] and returns a 
    datetime object. Assumes that the timezone is always -0700
    '''
    format = '[%d/%b/%Y:%H:%M:%S -0700]'
    timestamp = timestamp.strip()
    
    return datetime.strptime(timestamp, format)

def format_timedelta(td):
    '''
    Formats a timedelta object as a real valued number of seconds, with three
    decimal places of precision.
    '''
    
    return '%i.%03i' % (td.seconds, td.microseconds // 1000)

if __name__ == '__main__':
    main()
