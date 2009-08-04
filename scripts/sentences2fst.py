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
from nltk.corpus import wordnet
import linecache
from decimal import Decimal
import shutil

import pdb


LOG_LEVELS = {'debug': logging.DEBUG,
               'info': logging.INFO,
            'warning': logging.WARNING,
              'error': logging.ERROR,
           'critical': logging.CRITICAL}

ANEW_DB = os.path.expanduser('~/affect/word_data/anew_all.txt')
SENTI_DB = os.path.expanduser('~/affect/word_data/SentiWordNet_1.0.1.txt')
WORD_LIST_DIR = os.path.expanduser('~/affect/word_data/lists')

# all the possible FST options. Simple options are those that output a single
# unweighted output path.

FST_TYPES = ('pos', 'words', 'lemmas', 'lemmastems', 'senti', 'anew', 'lists')
SIMPLE_FST_TYPES = ('words', 'lemmas', 'pos', 'lemmastems')

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
    
    for fst_type in fst_types:
        if fst_type in SIMPLE_FST_TYPES:
            tag_sentences(sentence_dicts, fst_type)
            write_many_simple_fsts(sentence_dicts, fst_type)
        else:
            tag_sentences(sentence_dicts, fst_type)
            if fst_type == 'senti':
                write_many_multipath_fsts(sentence_dicts, fst_type)
            else:
                write_many_multipath_fsts(sentence_dicts, fst_type)
                
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
        sentence_dicts.extend(read_agree_sents(full_path))
    
    return sentence_dicts

def read_agree_sents(filename):
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
                words = tokenize_sentence(fields[2])
                
                sent_dict = {      'id' : sentence_id,
                              'emotion' : emotion,
                                'words' : words
                            }
                
                result.append(sent_dict)
            else:
                log.error('This line did not have 3 fields as expected: %s' % line)
                
                
    return result


def tokenize_sentence(sentence):
    '''
    Uses the default NLTK tokenizer, which as of July 2009 is the Penn
    TreeBank tokenizer which splits contractions. Also, strips off extra
    periods that might show up mid-sentence.
    
    >>> tokenize_sentence("""One day, I went to the store where a man said "Don't buy the milk"!""")
    ['one', 'day', ',', 'i', 'went', 'to', 'the', 'store', 'where', 'a', 'man', 'said', '"', 'do', "n't", 'buy', 'the', 'milk', '"', '!']
    >>> tokenize_sentence("""He said, "I am hungry." And then he went home.""")
    ['he', 'said', ',', '"', 'i', 'am', 'hungry', '.', '"', 'and', 'then', 'he', 'went', 'home', '.']
    
    '''
    words = [word.lower() for word in nltk.word_tokenize(sentence)]
    stripped_words = []
    
    # strip periods that the tokenizer left on
    for word in words:
        if word[-1] in ('.', ',') and len(word) > 1:
            stripped_words.extend([word[:-1], word[-1]])
        else:
            stripped_words.append(word)
    
    return stripped_words

def tag_sentences(sentence_dicts, tag_type):
    # check if it's already been tagged
    if tag_type in sentence_dicts[0]:
        return
    
    if tag_type == 'pos':
        [pos_tag_sentence(sent) for sent in sentence_dicts]
    elif tag_type == 'lemmas':
        log.debug('lemmatizing words')
        tag_sentences(sentence_dicts, 'pos')
        [lemmatize_sentence(sent) for sent in sentence_dicts]
    elif tag_type == 'lemmastems':
        tag_sentences(sentence_dicts, 'lemmas')
        [lemmastem_sentence(sent) for sent in sentence_dicts]
    elif tag_type == 'anew':
        anew = read_anew_db(ANEW_DB)
        [tag_anew_sentence(sent, anew) for sent in sentence_dicts]
    elif tag_type == 'senti':
        sentiwordnet = read_sentiwordnet(SENTI_DB)
        [tag_swn_sentence(sent, sentiwordnet) for sent in sentence_dicts]
    elif tag_type == 'lists':
        word_lists = read_word_lists(WORD_LIST_DIR)
        tag_sentences(sentence_dicts, 'lemmas')
        [tag_sentence_for_lists(sent, word_lists) for sent in sentence_dicts]
    elif tag_type == 'words':
        # do nothing for words
        pass


def pos_tag_sentence(sent_dict):
    '''
    Creates part of speech tags for each word in the sentence.
    
    >>> sent = {'words' : ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
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
    >>> lemmatize_sentence(sent)
    >>> sent['lemmas']
    ['So', 'the', 'father', 'give', 'him', 'his', 'bless', ',', 'and', 'with', 'great', 'sorrow', 'take', 'leave', 'of', 'him', '.']
    
    >>> sent = {'pos': ('IN', 'DT', 'NN', 'VBD', 'PRP', 'PRP$', 'NN', ',', 'CC', 'IN', 'JJ', 'NN', 'VBD', 'NN', 'IN', 'PRP', '.'), 'words': ['So', 'the', 'father', 'gave', 'him', 'his', 'blessing', ',', 'and', 'with', 'great', 'sorrow', 'took', 'leave', 'of', 'him', '.']}
    >>> lemmatize_sentence(sent)
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

def lemmastem_sentence(sent_dict):
def tag_swn_sentence(sent_dict, sentiwordnet):
    '''
    Looks up each lemma in SentiWordNet, by using the first synset for each
    lemma. If the word cannot be found, scores of 0 will be assigned. In order
    to look up each word in SentiWordnet, the words will be lemmatized and
    POS-tagged if they haven't been yet.
    '''
    # weights for matching synsets
    synset_weights = [1., 0.8, 0.6, 0.4, 0.2]
    
    if 'pos' not in sent_dict:
        pos_tag_sentence(sent_dict)
    
    if 'lemmas' not in sent_dict:
        lemmatize_sentence(sent_dict)
    
    pos_swn = []
    neg_swn = []
    
    for lemma, pos in zip(sent_dict['lemmas'], sent_dict['pos']):
        synsets = wordnet.synsets(lemma, wordnet_pos(pos))
        
        pos_value = 0.0
        neg_value = 0.0
        
        if synsets != []:
            for synset, weight in zip(synsets, synset_weights):
                synset_pair = (synset.pos, synset.offset)
            
                if synset_pair in sentiwordnet:
                    swn_values = sentiwordnet[synset_pair]
                    
                    pos_value += weight * swn_values['pos']
                    neg_value += weight * swn_values['neg']
        
        pos_swn.append(pos_value)
        neg_swn.append(neg_value)
    
    sent_dict['senti'] = {'pos' : pos_swn, 'neg' : neg_swn}

def tag_anew_sentence(sent_dict, anew):
    '''
    Attempts to tag the words in a sentence with their corresponding ANEW mean
    scores. For each word, it first looks up the word in ANEW and then if it
    is not found, looks up its lemma, if possible. If neither is found, it
    assigns a score of 5, the middle value on the ANEW score range.
    '''
    valence_list = []
    arousal_list = []
    dominance_list = []
    valence_arousal_list = []
    
    if 'lemmas' not in sent_dict:
        lemmatize_sentence(sent_dict)
    
    for word, lemma in zip(sent_dict['words'], sent_dict['lemmas']):
        valence = Decimal('5.')
        arousal = Decimal('0')
        dominance = Decimal('0')
        if word in anew:
            valence = anew[word]['valence']['mean']
            arousal = anew[word]['arousal']['mean']
            dominance = anew[word]['dominance']['mean']
        elif lemma in anew:
            valence = anew[lemma]['valence']['mean']
            arousal = anew[lemma]['arousal']['mean']
            dominance = anew[lemma]['dominance']['mean']
        
        valence = (valence - Decimal('5.')) / Decimal('4.')
        arousal /= Decimal('8.')
        dominance /= Decimal('8.')
        valence_arousal = valence * arousal
        
        valence_list.append(valence)
        arousal_list.append(arousal)
        dominance_list.append(dominance)
        valence_arousal_list.append(valence_arousal)
    
    sent_dict['anew'] = {'valence' : valence_list,
                         'arousal' : arousal_list,
                         'dominance' : dominance_list,
                         'valence*arousal' : valence_arousal_list}

def read_sentiwordnet(path):
    '''
    Returns a dictionary keyed by the pair (POS, offset). Each value is also
    a dictionary with three keys: 'pos', 'neg', 'terms'.
    
    >>> swn = read_sentiwordnet('/Users/bpg/cslu/affect/word_data/SentiWordNet_1.0.1.txt')
    >>> swn[('a', 1005286)] == {'neg': 0.125, 'terms': ['forlorn#a#1', 'godforsaken#a#2', 'lorn#a#1', 'desolate#a#2'], 'pos': 0.25}
    True
    '''
    sentiwordnet = {}
    
    for line in open(path):
        if not line.startswith('#') and line.strip() != '':
            fields = line.split()
            
            key = (fields[0], int(fields[1]))
            
            sentiwordnet[key] = { 'pos' : float(fields[2]),
                                  'neg' : float(fields[3]),
                                  'terms' : fields[4:]
                                }
    
    return sentiwordnet

def read_anew_db(path):
    '''
    Reads the ANEW.txt file into a dictionary keyed by word. Each value is
    also a dictionary with the following structure:
    {'abduction' : { 'word_num' : 621,
    'frequency' : 1,
    'valence' : { 'mean' : 2.76,
    'stdev' : 2.06},
    'arousal' : { 'mean' : 5.53,
    'stdev' : 2.43},
    'dominance' : { 'mean' : 3.49,
    'stdev' : 2.38}
    }
    }
    >>> anew = read_anew_db('/Users/bpg/cslu/affect/word_data/anew_all.txt')
    >>> anew['village'] == {'arousal': {'stdev': Decimal('1.87'), 'mean': Decimal('4.08')}, 'word_num': 477, 'valence': {'stdev': Decimal('1.34'), 'mean': Decimal('5.92')}, 'frequency': 72, 'dominance': {'stdev': Decimal('1.74'), 'mean': Decimal('4.94')}}
    True
    '''
    anew_dict = {}
    for line in open(path):
        fields = line.split('\t')
        
        if len(fields) == 9 and fields[1] != 'WdNum':
            if fields[8].startswith('.'):
                frequency = 0
            else:
                frequency = int(fields[8])
                
            word_dict = { 'word_num' : int(fields[1]),
                            'valence' : { 'mean' : Decimal(fields[2]),
                                         'stdev' : Decimal(fields[3])},
                            'arousal' : { 'mean' : Decimal(fields[4]),
                                         'stdev' : Decimal(fields[5])},
                          'dominance' : { 'mean' : Decimal(fields[6]),
                                         'stdev' : Decimal(fields[7])},
                          'frequency' : frequency
            }
            
            anew_dict[fields[0]] = word_dict
            
    return anew_dict

def read_word_lists(list_directory):
    '''
    Reads all files with a .list extension in a specified directory. Returns
    a dictionary keyed by words, where the values are lists of tags.
    '''
    words = {}
    
    for list_filename in os.listdir(list_directory):
        if list_filename.endswith('.list'):
            tag = os.path.splitext[list_filename][0]
            for word in open(os.path.join(list_directory, list_filename)):
                word = word.lowercase()
                
                if word not in words:
                    words[word] = [tag]
                else:
                    words[word].append(tag)

def tag_sentence_for_lists(sent_dict, lists_dict):
    '''
    Tries to tag sentences using the lists. If the word isn't found, look for
    corresponding lemma.
    '''
    sent_dict['lists'] = []
    for (word, lemma) in zip(sent_dict['words'], sent_dict['lemmas']):
        if word in lists_dict:
            sent_dict['lists'].extend(lists_dict[word])
        elif lemma in lists_dict:
            sent_dict['lists'].extend(lists_dict[lemma])
    

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

def create_symbol_table(sentence_dicts, key, filename):
    '''
    Writes a symbol table in the AT&T format to the specified filename.
    '''
    symbols = set()
    
    counter = 1
        
    f = open(filename, 'w')
    
    # write words
    for sent_dict in sentence_dicts:
        for word in sent_dict[key]:
            if word not in symbols:
                f.write('%s\t%i\n' % (word, counter))
                
                symbols.add(word)
                counter += 1
    
    f.close()

def write_simple_symbol_table(symbols, filename):
    f = open(filename, 'w')
    symbol_set = set(symbols)
    for index, symbol in enumerate(symbol_set):
        f.write('%s\t%i\n' % (symbol, index))
        
    
    f.close()

def write_many_simple_fsts(sent_dicts, key, basepath='./'):
    '''
    Writes a list of fsts to a directory. First creates a directory by
    appending key to basepath and writes over any existing directory.
    Then, writes a symbol file. Then, calls write_simple_fst for each 
    sentence. Finally creates an FST list file.
    '''
    fst_directory = os.path.join(basepath + key, 'fsts')
    symbol_path = os.path.join(fst_directory, "symbol_table.tsv")
    
    if os.path.exists(fst_directory):
        shutil.rmtree(fst_directory)
        
    os.makedirs(fst_directory)
    
    create_symbol_table(sent_dicts, key, symbol_path)
    
    for sent_no, sent_dict in enumerate(sent_dicts):
        fst_basepath = os.path.join(fst_directory, str(sent_no+1))
        
        write_simple_fst(sent_dict[key], symbol_path, fst_basepath)
        
    write_fst_list(sent_dicts, fst_directory, key)
    write_svm_input(sent_dicts, fst_directory)

def write_simple_fst(symbols, symbol_path, fst_basepath):
    '''
    Writes a simple fst containing a single path of symbols with no weights.
    A text representation of the FST is written to fst_path + ".txt" and then
    it is compile into a binary using fstcompile.
    '''
    fst = open(fst_basepath + ".txt", "w")
    
    # write arcs with each word
    state = 1
    for symbol in symbols:
        write_arc(fst, state, state+1, symbol, symbol)
        state += 1
    
    # write final state
    fst.write(str(state))
    fst.close()
    
    compile_fst(fst_basepath, symbol_path)

def write_many_multipath_fsts(sent_dicts, key, weight_range=None, split_values=False, basepath='./'):
    '''
    Writes a list of fsts to a directory. First creates a directory by
    appending key to basepath and writes over any existing directory.
    Then, writes a symbol file. Then, calls write_simple_fst for each 
    sentence. Finally creates an FST list file.
    '''
    fst_directory = os.path.join(basepath + key, 'fsts')
    symbol_path = os.path.join(fst_directory, "symbol_table.tsv")
    
    if os.path.exists(fst_directory):
        shutil.rmtree(fst_directory)
        
    os.makedirs(fst_directory)
    
    
    symbols = sent_dicts[0][key].keys()
    # add negative values for all symbols, even though they might not all be used
    neg_symbols = ['neg_%s' % symbol for symbol in symbols]
    symbols.extend(neg_symbols)
    
    if split_values:
        split_symbols = set()
        for symbol in symbols:
            split_symbols.add('%s_pos' % symbol)
            split_symbols.add('%s_neg' % symbol)
            split_symbols.add('%s_neutral' % symbol)
        
        write_simple_symbol_table(split_symbols, symbol_path)
    else:
        write_simple_symbol_table(symbols, symbol_path)
    
    for sent_no, sent_dict in enumerate(sent_dicts):
        fst_basepath = os.path.join(fst_directory, str(sent_no+1))
        
        write_multipath_fst(sent_dict[key], fst_basepath, symbol_path, 
                    weight_range=weight_range, split_values=split_values)
        
    write_fst_list(sent_dicts, fst_directory, key)
    write_svm_input(sent_dicts, fst_directory)

def write_multipath_fst(paths, fst_basepath, symbol_path, weight_range=None, split_values=False):
    '''
    
    '''
    first_state = 1
    last_state = 0
    current_state = 1
    
    fst = open(fst_basepath + ".txt", "w")
    
    for path_name, path in paths.iteritems():
        for index, value in enumerate(path):
            if split_values:
                midpoint = float(sum(weight_range)) / 2
                
                if value < midpoint:
                    label = '%s_neg' % path_name
                elif value > midpoint:
                    label = '%s_pos' % path_name
                else:
                    label = '%s_neutral' % path_name
                
                weight = abs(Decimal(str(value)) - Decimal(str(midpoint)))
            else:
                if value < 0:
                    weight = abs(value)
                    label = 'neg_%s' % path_name
                else:
                    weight = value
                    label = path_name
            
            if index == len(path) - 1:
                # if it's the last arc, connect to the last_state, instead of
                # state + 1
                write_arc(fst, current_state, last_state, label, label, weight=weight)
            elif index == 0:
                # write the first arc
                write_arc(fst, first_state, current_state+1, label, label, weight=weight)
            else:
                write_arc(fst, current_state, current_state+1, label, label, weight=weight)
            
            current_state += 1
        
    fst.write(str(last_state))
    fst.close()
    
    compile_fst(fst_basepath, symbol_path)

def write_arc(f, start_state, end_state, input_label, output_label, weight=None):
    '''
    Writes a line to the text FST file with a weight if specified.
    '''
    arc_fields = [str(start_state), str(end_state), input_label, output_label]
    
    if weight == 0:
        arc_fields.append('0')
    elif weight != None:
        arc_fields.append(str(weight))
    
    f.write('\t'.join(arc_fields) + '\n')

def compile_fst(fst_basepath, symbol_path):
    '''
    Calls fstcompile using the specified symbol table.
    '''
    parameters = [ "fstcompile", 
                   "--arc_type=log",
                   "--isymbols=%s" % symbol_path, 
                   "--osymbols=%s" % symbol_path, 
                   fst_basepath + ".txt",
                   fst_basepath + ".fst"]
    
    subprocess.call(parameters)

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

def stem_word(word):
    '''
    Applies the Porter Stemmer to a word.
    
    >>> stem_word('lying')
    'lie'
    >>> stem_word('helpful')
    'help'
    >>> stem_word('really')
    'realli'
    '''
    porter = nltk.PorterStemmer()
    
    return porter.stem(word)
    
def wordnet_pos(pos_tag):
    '''
    Returns 'a', 'r', 'n', or 'v' corresponding to adjective, adverb, noun
    and verb, respectively. Return None if there's no match
    '''
    
    prefixes = { 'JJ' : wordnet.ADJ,
                 'NN' : wordnet.NOUN,
                 'RB' : wordnet.ADJ,
                 'VB' : wordnet.VERB
    }
    
    return prefixes.get(pos_tag[:2])

def write_fst_list(sentence_dicts, fst_directory, key):
    """
    Writes an fst list file one level above fst_directory for all of the sentences. 
    Line numbers should correspond to sentence indices in list of dicts. 
    """
    list_file_path = os.path.join(fst_directory, '..', key + '.fstlist')
    
    f = open(list_file_path, 'w')
    
    for index in range(1, len(sentence_dicts)+1):
        filename = os.path.join(fst_directory, str(index) + '.fst')
        f.write('%s\n' % os.path.realpath(filename))
        
        #f.write('./fsts/%i.fst\n' % index)
        
    f.close()

def write_svm_input(sentence_dicts, fst_directory, train_percentage=0.8):
    '''
    Writes test and train files for input to LIBSVM. Also writes a file 
    containing all of the sentences
    '''
    train_path = os.path.join(fst_directory, 'sentences.train')
    test_path = os.path.join(fst_directory, 'sentences.test')
    all_path = os.path.join(fst_directory, 'sentences.all')
    
    training_size = int(round(train_percentage*len(sentence_dicts)))
    train_list = random.sample(sentence_dicts, training_size)
    
    
    train_file = open(train_path, 'w')
    test_file  = open(test_path, 'w')
    all_file = open(all_path, 'w')
    
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
    if sys.argv[1] == 'test':
        import doctest
        doctest.testmod(verbose=False)
    else:
        main()
