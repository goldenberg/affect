#!/usr/bin/env python
# encoding: utf-8
"""
untitled.py

Created by Benjamin Goldenberg on 2009-06-17.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

import sys
import optparse
import logging
import subprocess
import random
import os
import re

import pdb

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

# punctuation that is worth parsing as a separate token. all other punctuation
# is ignored. ellipses would be nice to parse as a token, but I couldn't figure
# out how to escape them.

SPECIAL_PUNCTUATION = ['?', '!', '&']

logging.basicConfig()
log = logging.getLogger("sentences2fst")

def main():
    usage = """%prog [options] SENTENCE_DIRECTORY 
            """
    
    opt_parser = optparse.OptionParser(usage=usage)
    
    opt_parser.add_option("-l", "--log_level", action="store", 
                       default='debug', dest="log_level", 
                       help="Logging level. One of {'debug', 'info', 'warning', 'error', 'critical'}")
    
    opt_parser.add_option("-s", "--symbol_table", action='store', 
                       default='symbol_table.tsv', dest='symbol_table',
                       help='Filename to store the word symbol table.')
    
    options, arguments = opt_parser.parse_args()
    
    log.setLevel(LOG_LEVELS[options.log_level])
    
    sentence_directory = arguments[0]
    symbol_filename = options.symbol_table
    sentence_dicts = []
    
    for sent_filename in os.listdir(sentence_directory):
        full_path = os.path.join(sentence_directory, sent_filename)
        sentence_dicts.extend(read_agree_sent(full_path))
    
    create_symbol_table(sentence_dicts, options.symbol_table)
    
    if not os.path.exists('data'):
        os.mkdir('data')
    
    for index, sent_dict in enumerate(sentence_dicts):
        write_fst(sent_dict, symbol_filename, 'data/%i' % (index + 1))
    
    write_fst_list(sentence_dicts)
    write_svm_input(sentence_dicts)

def create_symbol_table(sentence_dicts, filename):
    '''
    Writes a symbol table in the AT&T format to the specified filename.
    '''
    words = set()
    counter = 1
        
    f = open(filename, 'w')
    
    for sent_dict in sentence_dicts:
        for word in sent_dict['words']:
            if word not in words:
                f.write('%s\t%i\n' % (word, counter))
                
                words.add(word)
                counter += 1
    
    f.close()

def write_fst(sent_dict, symbol_path, fst_path):
    '''
    Converts a sentence to an fst and writes it to emotion_id/sent_id.txt.
    Then compiles the FST using fstcompile. fst_path should be the basename
    without an extension.
    '''
    f = open(fst_path + ".txt", "w")
    
    # write arcs with each 
    state = 1
    for word in sent_dict['words']:
        arc_fields = [str(state), str(state+1), word, word]
        f.write('\t'.join(arc_fields) + '\n')
        state += 1
    
    # write final state
    f.write(str(state))
    f.close()
    
    parameters = [ "fstcompile", 
                   "--arc_type=log",
                   "--isymbols=%s" % symbol_path, 
                   "--osymbols=%s" % symbol_path, 
                   fst_path + ".txt", 
                   fst_path + ".fst"]
    #log.debug('fst parameters: %s' % ' '.join(parameters))
    
    subprocess.call(parameters)

def read_agree_sent(filename):
    '''
    Returns a list of dictionaries with 3 keys:

    1) 'id' : sentence id (string)
    2) 'emotion' : emotion id (string)
    3) 'words' : the parsed words and interesting punctuation (list of strings)
    '''

    result = []

    regex = re.compile(r"[\w']+|[%s]" % ''.join(SPECIAL_PUNCTUATION))

    for line in open(filename):
        if line.strip() != '':
            fields = line.split('@')
            if len(fields) == 3:
                words = [word.upper() for word in regex.findall(fields[2])]
                sent_dict = { 'id' : fields[0],
                              'emotion' : fields[1],
                              'words' : words }

                result.append(sent_dict)
            else:
                log.error('This line did not have 3 fields as expected: %s' % line)

    return result

def write_fst_list(sentence_dicts):
    """
    Writes an fst list for all of the sentences. Line numbers should 
    correspond to sentence 
    """
    
    # dictionary of file objects, keyed by emotion id (string)
    f = open('list.fst', 'w')
    
    for index in range(1, len(sentence_dicts)+1):
        f.write('data/%i.fst\n' % index)
    
    f.close()

def write_svm_input(sentence_dicts, train_percentage=0.8):
    '''
    Writes test and train files for input to LIBSVM. Also writes a file 
    containing all of the sentences
    '''
    training_size = int(round(train_percentage*len(sentence_dicts)))
    train_list = random.sample(sentence_dicts, training_size)
    
    train_file = open('sentences.train', 'w')
    test_file  = open('sentences.test', 'w')
    all_file = open('sentences.all', 'w')
    for index, sent_dict in enumerate(sentence_dicts):
        line = '%s %i:1.0\n' % (sent_dict['emotion'], index+1)
        if sent_dict in train_list:
            train_file.write(line)
        else:
            test_file.write(line)
        
        all_file.write(line)
    
    train_file.close()
    test_file.close()
    all_file.close()
if __name__ == "__main__":
    main()
