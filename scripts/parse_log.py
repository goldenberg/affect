#!/usr/bin/env python2.6
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
import cgi
import logging
import pdb

from datetime import datetime, time, timedelta

# Format copied and pasted from Apache conf - use raw string + single quotes
apache_format = r'%h %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\"'
apache_parser = apachelog.parser(apache_format)

logging.basicConfig(level=logging.INFO)

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
                            help='Collapse the rating parameter into two classes (plus neutral)'
                            ' (i.e. group {1,2}, {3}, {4,5})')
    opt_parser.add_option("-i", "--shortip", dest="short_ip", action="store_true", default=False,
                            help="Only filter the requests based on the first three"
                            " bytes of the IP address. (XXX.XXX.XXX.YYY)")
    opt_parser.add_option("-w", "--timewindow", action="store", type=int, default=300,
                            help="Window for matching HTTP request to timestamp in filename in seconds. Default 300s")
    
    options, arguments = opt_parser.parse_args()
    
    wav_filename = arguments[0]
    log_filename = arguments[1]
    base_filename= os.path.splitext(wav_filename)[0]
    out_filename = base_filename + '.tsv'
    
    log_file = open(log_filename)
    wav_time = parse_wav_timestamp(wav_filename)
    
    # read delays and classes if specified at the command line
    if options.delays_filename:
        InterviewStage.read_delays_file(options.delays_filename)
        
    if options.classes_filename:
        InterviewStage.read_classes_file(options.classes_filename)
        
    all_requests = parse_file(log_filename)
    filtered_requests = filter_requests(wav_time, all_requests, short_ip=options.short_ip)    
    stages = construct_stages(wav_time, filtered_requests)
    
    pdb.set_trace()
    #stats = format_summary_statistics(stage_dicts, ip_address)
    #print stats
    
    write_stage_output(stages, out_filename)
    
    if options.svm_output:
        if not options.classes_filename:
            logging.error("In order to generate a file for pitch, formants and energy analysis, you must also specify classes.")
        else:
            svm_filename = os.path.splitext(wav_filename)[0] + '.svmin'
            write_svm_output(stage_dicts, wav_filename, svm_filename)
    
    

def parse_entire_file(log_file, ip_address, wav_time, use_rating_parameter=True, delays={}, classes={}):
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
    
    # sometimes it's ne
    next_rating = -1
    
    for line in log_file:
        if line.strip() == '':
            continue
        if is_line_relevant(line, ip_address):
            logging.debug("The line is relevant: %s" % line)
            
            (host, log_time, request, referer, user) = parse_line(line)
            if last_request == '':
                # first relevant line
                last_request = request
                continue
            else:
                last_request_dict = parse_request(last_request, delays=delays)
                current_request_dict = parse_request(request, delays=delays)
                
                start_time = current_request_dict['time'] - last_request_dict['duration'] - wav_time
                end_time = current_request_dict['time'] - wav_time
                
                stage_dict = {       "name" : last_request_dict['name'], 
                               "start_time" : start_time,
                                 "end_time" : end_time }
                
                if next_rating and stage_dict['name'].startswith('slide'):
                    # use the old rating and then reset it
                    stage_dict['class'] = next_rating
                    next_rating = None
                
                if 'rating' in last_request_dict and use_rating_parameter:
                    if stage_dict['name'].startswith('slide'):
                        stage_dict['class'] = last_request_dict['rating']
                    else:
                        # store the rating until it can be used later
                        # this needs to be done at the picRating stage
                        # otherwise, the rating gets lost
                        next_rating = last_request_dict['rating']
                elif last_request_dict['name'] in classes:
                    stage_dict["class"] = classes[last_request_dict['name']]
                
                output_dicts.append(stage_dict)
                
                last_request = request
                
                if stage_dict['name'] == 'videoRecall':
                    # we've reached the end
                    break
    
    # deal with last request, which should be the video recall stage
    # assume that the request is served instantly
    
    if last_request == '':
        logging.error("There were no relevant lines.")
        return []
    try:
        final_request_dict = parse_request(last_request, delays=delays)
    except ValueError:
        # there was a problem parsing. hopefully this line wasn't supposed to 
        # be relevant...
        log.warning("There was a problem parsing the last line: %s" % last_request)
    
    start_time = final_request_dict['time'] - wav_time
    end_time = final_request_dict['time'] - wav_time + final_request_dict['duration']
    
    fields = [final_request_dict['name'], format_timedelta(start_time), format_timedelta(end_time)]
    
    stage_dict = { "name"       : final_request_dict['name'], 
                   "start_time" : start_time,
                   "end_time"   : end_time }
    
    if 'rating' in last_request_dict and use_rating_parameter:
        stage_dict['class'] = last_request_dict['rating']
    if final_request_dict['name'] in classes:
        stage_dict["class"] = classes[final_request_dict['name']]
    
    output_dicts.append(stage_dict)
    
    return output_dicts

def parse_file(log_filename):
    '''
    Reads the entire file into a list of request objects. This function will
    replace parse_entire_file.
    '''
    requests = []
    
    for line in open(log_filename):
        if line.strip != '':
            request = HTTPRequest(line)
            requests.append(request)
    
    return requests

def find_first_request(wav_time, requests):
    '''
    Finds the request for http://www.csee.ogi.edu/~zak/sesdc/ that occured
    closest to the wav_time.
    
    wav_time should be a datetime object and window is the number of
    seconds within which to locate the request.
    
    Returns the closest_request. Returns None if there was no matching request
    ''' 
    closest_request = None
       
    for current_request in requests:
        if current_request.url_components.path.endswith('/~zak/sesdc/index2.html'):
            logging.debug("I found a request to index2.html at time %s" % current_request.time)
            
            # if we haven't found a request to index2.html yet, set closest=current
            # if current is closer to the target time, set closest = current
            # otherwise, do nothing
            if not closest_request:
                closest_request = current_request
            elif abs(closest_request.time - wav_time) > (current_request.time - wav_time):
                closest_request = current_request
    
    if not closest_request:
        logging.error('Could not find a request to index2.html in the log file')
    else:
        logging.info('Found a request to ~zak/sesdc/index2.html at %s, which is %s after the wav time.'
                        % (closest_request.time, closest_request.time - wav_time))
    
    return closest_request
    

def filter_requests(wav_time, requests, short_ip=False):
    '''
    Finds the first request and then filters the rest of the requests for 
    only those with matching IP address and to relevant paths, etc.
    '''
    
    first_request = find_first_request(wav_time, requests)
    first_request_index = requests.index(first_request)
    ip_address = first_request.host
    
    if short_ip:
        # chop off the last component of the IP address
        ip_address = '.'.join(ip_address.split('.')[:-1])
    
    filtered_requests = []
    
    for request in requests[first_request_index:]:
        if request.is_request_relevant(ip_address):
            filtered_requests.append(request)
    
    return filtered_requests

def construct_stages(wav_time, requests):
    '''
    Builds a list of interview stages from the filtered HTTPRequests. 
    '''
    stages = []
    
    previous_request = requests[0]
    previous_stage = InterviewStage(previous_request)
    next_rating = None
    
    for request in requests[1:]:
        current_stage = InterviewStage(request)
        
        # we only set the start_time because the duration was parsed out of the
        # request and end_time is a computed property
        previous_stage.start_time = current_stage.client_time - previous_stage.duration - wav_time
        
        if next_rating and current_stage.is_slide(): 
            # if there's a stored rating and the currentstage is a slide
            # use the old rating and then reset it
            current_stage.rating = next_rating
            next_rating = None
        
        if 'rating' in current_request.url_args:
            if previous_stage.is_slide():
                previous_stage.rating = current_request.url_args['rating'][0]
            else:
                # store the rating until it can be used later
                # this needs to be done at the picRating stage
                # otherwise, the rating gets lost
                next_rating = previous_request.url_args['rating'][0]
        
        stages.append(previous_stage)
        
        previous_stage = current_stage
        previous_request = request
        
        if current_stage.name == 'videoRecall':
            # we've reached the end of the interview
            # we have to assume that the request was served instantly since there will
            # be no following stage with a start time.
            current_stage.start_time = str2datetime(request.url_args['client_time'][0]) - wav_time
            stages.append(current_stage)
            break
   
    return stages

def write_stage_output(stages, out_filename, stats=None):
    '''
    Writes a the stage dictionaries to a file, separated by newlines.
    '''
    f = open(out_filename, 'w')
    
    # print header
    if stats:
        stats_lines = stats.split('\n')
        for line in stats_lines:
            f.write('# %s\n' % line)
        
    for stage in stages:
        fields = [stage.name, format_timedelta(stage.start_time), format_timedelta(stage.end_time)]
        #if stage.has_rating():
        #    fields.append('%+i' % stage.rating)
        
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

def format_summary_statistics(stage_dicts, ip_address):
    '''
    Prints summary statistics to stdout, including number of stages, time period,
    start time.
    '''
    start_time = stage_dicts[0]['start_time']
    end_time = stage_dicts[-1]['end_time']
    duration = end_time - start_time
    
    slide_count = len(filter(lambda stage: stage['name'].startswith('slide'), stage_dicts))

    return 'Log parsed on: %s\nIP address: %s\nFirst stage start: %s\nInterview Duration: %s\n# of Slides: %i' % (
        ip_address,
        datetime.now(),
        format_timedelta_as_time(start_time), 
        format_timedelta_as_time(duration), slide_count)
    
    
def parse_wav_timestamp(wav_filename):
    '''
    Returns a datetime object extracted from the wav filename. Should 
    correspond to the beginning of the recording.
    
    >>> get_wav_timestamp('2009-05-20_09-49-28_l0_.wav')
    datetime.datetime(2009, 5, 20, 9, 49, 28)
    '''
    basename = os.path.splitext(os.path.basename(wav_filename))[0]
    
    format = '%Y-%m-%d_%H-%M-%S_l0_'
    
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
    try:
        return '%i.%03i' % (td.seconds, td.microseconds // 1000)
    except Exception, e:
        pdb.set_trace()
        raise e

def format_timedelta_as_time(td):
    '''
    Formats a timedelta as MM:SS.MMM.
    '''
    return '%02i:%02i.%03i' % (td.seconds // 60, td.seconds % 60, td.microseconds // 1000)

def str2datetime(s):
    # replace last colon with dot
    parts = s.split(':')
    hours_mins_secs = ':'.join(parts[:3])
    dt = datetime.strptime(hours_mins_secs, "%H:%M:%S")
    return dt.replace(microsecond=int(parts[3]))

class HTTPRequest(object):
    """Represents a single request to the server. Created from log line"""
    def __init__(self, line):
        super(HTTPRequest, self).__init__()
        data = apache_parser.parse(line)
        self.host = data['%h']
        self.time = parse_timestamp(data['%t'])
        self.request = data['%r']
        self.referer = data['%{Referer}i']
        self.user = data['%u']
        
        # request is "GET /~zak/... HTTP/1.0"
        request_fields = self.request.split(' ')
        self.url = request_fields[1]
        self.url_components = urlparse.urlparse(self.url)
        self.parse_url_args()
    
    def __str__(self):
        return '%s from %s at %s' % (self.url, self.host, self.time)
    
    def parse_url_args(self):
        '''
        Parses the request to set self.url_args.
        '''
        try:
            self.url_args = urlparse.parse_qs(self.url_components.query)
        except AttributeError, e:
            # python 2.5 moved parse_qs to urlparse from cgi
            # there's probably a cleaner way to check whether we're using 2.5 or 2.6
            # but this seems to work for now.
            self.url_args = cgi.parse_qs(self.url.url_components.query)
    
    def is_request_relevant(self, ip):
        '''
        Determines whether the request is relevant to the interview. Should match
        the IP address, have the appropriate url arguments, and be a request
        to the right path.
        '''
        
        return ('client_time' in self.url_args and 
                'show_param' in self.url_args and
                '/~zak/sesdc/' in self.url_components.path and
                self.host.startswith(ip) )
    
    @property
    def page_name(self):
        '''
        Returns the page requested, without an extension.
        '''
        return os.path.splitext(os.path.basename(self.url_components.path))[0]
        
class InterviewStage(object):
    """Represents a single stage of the interview (e.g. slide or recall)"""
    def __init__(self, request):
        super(InterviewStage, self).__init__()
        
        self.set_stage_name(request.page_name)
        self.client_time = str2datetime(request.url_args['client_time'][0])
        
        if request.page_name in InterviewStage.delays:
            self.duration = InterviewStage.delays[request.page_name]
        else:
            self.duration = timedelta(seconds=int(request.url_args['show_param'][0]))
        
    def __repr__(self):
        '''
        Returns a simple representation of the interview: "slideXYZ 1:23 to 2:34 rating 4"
        '''
        representation = '%s %s to %s' % (self.name, format_timedelta_as_time(self.start_time),
                                format_timedelta_as_time(self.end_time))
        
        if hasattr(self, 'rating'):
            representation += ' rating %s' % self.rating
        
        return representation
    
    @property
    def end_time(self):
        '''
        Returns start_time + duration
        '''
        if hasattr(self, 'duration'):
            return self.start_time + self.duration
        else:
            return None
    
    @end_time.setter
    def end_time(self, value):
        """
        Sets duration to end_time - start_time. Raises a ValueError if start_time
        is None
        """
        if self.start_time:
            self.duration = value - self.start_time
        else:
            raise ValueError("start_time must be set before setting end_time")
    
    def set_stage_name(self, pagename):
        '''
        Sets self.name from the pagename. sam1 -> picRating, sam2 -> vidRating,
        1234 -> slide1234.
        '''
        
        if pagename == 'sam1':
            self.name = 'picRating'
        elif pagename == 'sam2':
            self.name = 'vidRating'
        elif pagename in ('picRecall', 'videoRecall'):
            self.name = pagename
        else:
            self.name = 'slide' + pagename
    
    def is_slide(self):
        '''
        Returns true if the name of the stage starts with 'slide'
        '''
        return self.name.startswith('slide')
    
    @property
    def rating(self):
        '''
        Returns the rating
        '''
        return self._rating
    
    @rating.setter
    def rating(self, value):
        """Casts value to an int and sets the rating"""
        self._rating = int(value)
        
        
    def has_rating(self):
        '''
        True if the stage has an associated rating. False otherwise.
        '''
        try:
            self._rating
            return True
        except AttributeError, e:
            return False
        
        
    @classmethod
    def read_delays_file(cls,filename):
        '''
        Reads a TSV file with two columns: slide name and duration in seconds. 
        Returns a dictionary of timedelta objects keyed by slide names (with no 
        file extensions).
        '''
        cls.delays = {}
        
        for line in open(filename):
            fields = line.split('\t')
            cls.delays[fields[0]] = timedelta(seconds=int(fields[1]))
    
    @classmethod
    def read_classes_file(cls, filename):
        '''
        Reads a TSV file with two columns: slide name and a classification 
        Returns a dictionary of integers keyed by slide names (with no 
        file extensions).
        '''
        cls.classes = {}
        
        for line in open(filename):
            fields = line.split('\t')
            cls.classes[fields[0]] = int(fields[1])
    
if __name__ == '__main__':
    main()
