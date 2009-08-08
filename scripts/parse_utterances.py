#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-08-06.
Copyright (c) 2009. All rights reserved.
"""

import sys
import optparse
import logging
import pdb

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

log = logging.getLogger('parse_utterances.py')

def main():
    usage = """%prog STAGE_TSV CTM_FILE OUTPUT_FILE [options]
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-l", "--log_level", action="store_true", 
                       default='warning', dest="log_level")
    
    options, arguments = opt_parser.parse_args()
    logging.basicConfig()
    log.setLevel(LOG_LEVELS[options.log_level])
    
    if len(arguments) != 3:
        log.error('There should be exactly three arguments.')
    
    stages_tsv = arguments[0]
    ctm_filename = arguments[1]
    output_filename = arguments[2]
    
    stage_dicts = read_stages(stages_tsv)
    read_ctm_file(ctm_filename, stage_dicts)
    write_utterances(output_filename, stage_dicts)
    

def read_stages(stage_tsv):
    '''
    Returns a list of dictionaries with the following keys: 'id', 
    'start_time', 'end_time', 'words', 'class' (optional)
    '''
    stage_dicts = []
    
    for line in open(stage_tsv):
        if line.strip() != '':
            fields = line.split()
            stage_dict = {}
            
            if fields[0].startswith('slide'):
                stage_dict['id'] = fields[0][5:]
            else:
                stage_dict['id'] = fields[0]
                
            stage_dict['start_time'] = float(fields[1])
            stage_dict['end_time'] = float(fields[2])
            stage_dict['words'] = []
            
            if len(fields) > 3 and fields[3].strip() != '':
                stage_dict['class'] = int(fields[3])
                
            stage_dicts.append(stage_dict)
            
    return stage_dicts

def read_ctm_file(ctm_filename, stage_dicts):
    '''
    Reads the CTM file and adds words to the stage dicts.
    '''
    
    for line in open(ctm_filename):
        fields = line.split()
        start_time = float(fields[2])
        word = fields[4].strip()[:-4]
        word = word.replace('@', '#')
        
        if word not in ('<s>', '</s>'):
            stage = find_current_stage(start_time, stage_dicts)
#            pdb.set_trace()
            if stage:
                log.debug('found a stage')
                stage['words'].append(word)

def write_utterances(filename, stage_dicts):
    '''
    Writes out the utterances to a file suitable for input to sentences2fst.
    Ignores any stages without ratings.
    '''
    
    output = open(filename, 'w')
    
    for stage in stage_dicts:
        if 'class' in stage:
            output.write('%s@%s@%s\n' % (stage['id'], stage['class'], ' '.join(stage['words'])))
    
    output.close()


def find_current_stage(time, stage_dicts):
    '''
    Finds the current stage as of a given time. time should be a float. (seconds)
    '''
    for stage in stage_dicts:
        if time >= stage['start_time'] and time <= stage['end_time']:
            return stage
    
    if time > stage['end_time']:
        # time occurs after the end
        return None


if __name__ == "__main__":
    main()

