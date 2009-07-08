#!/usr/bin/env python
# encoding: utf-8
"""
sentences2fst.py

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
import nltk
import linecache
import pdb

LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

FST_TYPES = ('pos', 'words', 'lemmas', 'senti', 'anew')

# punctuation that is worth parsing as a separate token. all other punctuation
# is ignored. ellipses would be nice to parse as a token, but I couldn't figure
# out how to escape them.

SPECIAL_PUNCTUATION = ['?', '!', '&']

WORDNET_POS = { 'a' : ['JJ', 'JJR', 'JJS'], #adjectives
                'r' : ['RB', 'RBR', 'RBS'],
                'n' : ['NN', 'NNS', 'NNP', 'NNPS'],
                'v' : ['VB', 'VBD', 'VBG', 'VBN', 'VBZ']
}

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
    
    opt_parser.add_option("-p", "--pos_directory", action='store', 
                        help="A directory of POS files to be read. Creates"
                        "a parallel path in the FST")
    
    options, arguments = opt_parser.parse_args()
    
    log.setLevel(LOG_LEVELS[options.log_level])
    
    fst_types, other_args = parse_args(arguments)
    
    sentence_directory = other_args[0]
    symbol_filename = options.symbol_table
    
    sentence_dicts = read_agree_sentence_directory(sentence_directory)
    
    
    create_symbol_table(sentence_dicts, options.symbol_table)
    
    if not os.path.exists('data'):
        os.mkdir('data')
    
    for index, sent_dict in enumerate(sentence_dicts):
        write_fst(sent_dict, symbol_filename, 'data/%i' % (index + 1))
    
    write_fst_list(sentence_dicts)
    write_svm_input(sentence_dicts)

def parse_args(arguments):
    '''
    Returns a pair: a list of the fst output types and a list of any other args.
    
    >>> parse_args(['words', 'anew', './foo', './bar'])
    (['words', 'anew'], ['./foo', './bar'])    
    '''
    fst_types = []
    other_args = []
    
    for arg in arguments:
        if arg in FST_TYPES:
            fst_types.append(arg)
        else:
            other_args.append(arg)
    
    return fst_types, other_args

def read_agree_sentence_directory(sentence_directory):
    '''
    Reads a directory of high agree sentences into sentence dicts.
    '''
    sentence_dicts = []
    
    for sent_filename in os.listdir(sentence_directory):
        full_path = os.path.join(sentence_directory, sent_filename)
        sentence_dicts.extend(read_agree_sents(full_path, options.pos_directory))
    
    return sentence_dicts

def read_agree_sents(filename, pos_directory):
    '''
    Returns a list of dictionaries with 4 keys:
    
    1) 'id' : sentence id (int)
    2) 'emotion' : emotion id (int)
    3) 'words' : the parsed words and interesting punctuation (list of strings)
    4) 'pos'
    '''
    
    result = []
    story_name = os.path.splitext(os.path.basename(filename))[0]
    
    for line in open(filename):
        if line.strip() != '':
            fields = line.split('@')
            if len(fields) == 3:
                sentence_id = int(fields[0])
                emotion = int(fields[1])
                words = nltk.word_tokenize(fields[2])
                
                sent_dict = {      'id' : sentence_id,
                              'emotion' : emotion,
                                'words' : words
                            }
                
                result.append(sent_dict)
            else:
                log.error('This line did not have 3 fields as expected: %s' % line)
                
                
    return result


def pos_tag_sentence(sent_dict):
    '''
    Creates part of speech tags for each word in the sentence.
    
    >>> sent = {'words' : ['So', 'the', 'father', 'gave', 'him', 'his', 
    'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']
    >>> pos_tag_sentence(sent)
    >>> sent['pos']
    ('IN', 'DT', 'NN', 'VBD', 'PRP', 'PRP$', 'NN', ',', 'CC', 'IN', 'JJ', 'NN', 'VBD', 'NN', 'IN', 'PRP', '.')
    '''
    
    word_tag_pairs = nltk.pos_tag(sent_dict['words'])
    
    # unzip the pairs using zip(*)
    sent_dict['pos'] = zip(*word_tag_pairs)[1]

def lemmatize_sentence(sent_dict):
    '''
    Adds lemmas to the sent_dict using the WordNet lemmatizer. It will be
    more accurate if pos tags also exist. If they don't, it will try them all
    until it finds one that creates a new lemma.
    
    >>> sent = {'words': ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> sf.lemmatize_sentence(sent)
    >>> sent['lemmas']
    ['So', 'the', 'father', 'give', 'him', 'his', 'bless', ',', 'and', 'with', 'great', 'sorrow', 'take', 'leave', 'of', 'him', '.']
    
    >>> sent = {'pos': ('IN', 'DT', 'NN', 'VBD', 'PRP', 'PRP$', 'NN', ',', 'CC', 'IN', 'JJ', 'NN', 'VBD', 'NN', 'IN', 'PRP', '.'), 'words': ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> sent['lemmas']
    ['So', 'the', 'father', 'give', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'take', 'leave', 'of', 'him', '.']
    '''
    if 'pos' in sent_dict:
        # use the POS tags
        lemmas = []
        for word, pos in zip(sent_dict['words'], sent_dict['pos']):
            lemmas.append(lemmatize_word(word, pos))
        
        sent_dict['lemmas'] = lemmas
    else:
        sent_dict['lemmas'] = [lemmatize_word(word) for word in sent_dict['words']]

def read_pos_sentence(sentence_id, story, pos_directory):
    '''
    Reads the parts of speech and the words for a specified sentence in a
    given story. The sentence_id is a 0-indexed int from the *.agree files.
    Returns a dictionary with two keys:
    
    words: a list of stemmed words
    pos: a list of parts of speech (as defined in the original corpus)
    
    words and pos should be the same length (so, they can easily be zipped together)
    '''
    word_list = []
    pos_list  = []
    
    filename = os.path.join(pos_directory, '%s.sent.okpuncs.props.pos' % story)
    
    line = linecache.getline(filename, sentence_id+1)
    
    for token in re.findall('\(.*?\)', line):
        # each token will be of the form (POS Word) (e.g. (RB Long))
        fields = token.split()
        pos = fields[0][1:]
        word = fields[1][:-1]
        
        if word.isalpha():
            word = lemmatize_word(word, pos)
            word_list.append(word.upper())
            pos_list.append(pos)
        else:
            if word in SPECIAL_PUNCTUATION:
                word_list.append(word)
                pos_list.append('.')
                
    assert len(word_list) == len(pos_list)
    
    return {'words' : word_list, 'pos' : pos_list}

def create_symbol_table(sentence_dicts, filename):
    '''
    Writes a symbol table in the AT&T format to the specified filename.
    '''
    symbols = set()
    
    counter = 1
        
    f = open(filename, 'w')
    
    # write words
    for sent_dict in sentence_dicts:
        for word in sent_dict['words']:
            if word not in symbols:
                f.write('%s\t%i\n' % (word, counter))
                
                symbols.add(word)
                counter += 1
    
    # write pos
    for sent_dict in sentence_dicts:
        for pos in sent_dict['pos']:
            if pos not in symbols:
                f.write('%s\t%i\n' % (pos, counter))
                
                symbols.add(pos)
                counter += 1
    
    f.close()

def write_fst(sent_dict, symbol_path, fst_path):
    '''
    Converts a sentence to an fst and writes it to emotion_id/sent_id.txt.
    Then compiles the FST using fstcompile. fst_path should be the basename
    without an extension.
    '''
    f = open(fst_path + ".txt", "w")
    
    # write arcs with each word
    state = 1
    state = 1
    for word in sent_dict['words']:
        write_arc(f, state, state+1, word, word)
        state += 1
    
    # write arcs with each pos
    last_state = state
    last_pos = sent_dict['pos'][-1]
    
    # write the first pos arc (originating from state 1)
    first_pos = sent_dict['pos'][0]
    state += 1
    write_arc(f, 1, state, first_pos, first_pos)
    
    for pos in sent_dict['pos'][1:-1]:
        write_arc(f, state, state+1, pos, pos)
        state += 1
    
    # write last pos arc (ending at same ending state)
    write_arc(f, state, last_state, last_pos, last_pos)
    
    # write final state
    f.write(str(last_state))
    f.close()
    
    parameters = [ "fstcompile", 
                   "--arc_type=log",
                   "--isymbols=%s" % symbol_path, 
                   "--osymbols=%s" % symbol_path, 
                   fst_path + ".txt", 
                   fst_path + ".fst"]
    #log.debug('fst parameters: %s' % ' '.join(parameters))
    
    subprocess.call(parameters)

def write_arc(f, start_state, end_state, input_label, output_label):
    arc_fields = [str(start_state), str(end_state), input_label, output_label]
    f.write('\t'.join(arc_fields) + '\n')

def lemmatize_word(word, pos=None):
    '''
    Tries to lemmatize a word. If a POS is specified, it uses the corresponding 
    Wordnet tag, if possible. If a POS is not specified, all the tags are tried
    until a different word is returned. If nothing is found, return the original
    word.
    
    >>> lemmatize_word('youngest', 'JJS')
    'young'
    >>> lemmatize_word('brought', 'VBD')
    'bring'
    
    '''
    lemmatizer = nltk.stem.WordNetLemmatizer()
    
    
    if pos:
        wordnet_pos_tag = wordnet_pos(pos)
    else:
        wordnet_pos_tag = None
    
    if wordnet_pos_tag:
        return lemmatizer.lemmatize(word, wordnet_pos_tag)
    else:
        for tag in ['a', 'r', 'n', 'v']:
            root = lemmatizer.lemmatize(word, tag)
            if root != word:
                return root
    
    # if we haven't found anything by here, just return the word.
    return word

def wordnet_pos(pos_tag):
    '''
    Returns 'a', 'r', 'n', or 'v' corresponding to adjective, adverb, noun
    and verb, respectively. Return None if there's no match
    '''
    
    prefixes = { 'JJ' : 'a',
                 'NN' : 'n',
                 'RB' : 'r',
                 'VB' : 'v'
    }
    
    return prefixes.get(pos_tag[:2])

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
