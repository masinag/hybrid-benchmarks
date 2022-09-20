
import numpy as np
import os
from pysmt.shortcuts import BOOL, LE, Plus, REAL, Real, Symbol, Times, reset_env
from string import ascii_letters

from wmibench import wmibench_path

# full UCI suite sorted by increasing number of features
EXPERIMENTS = {'small' : ['balance-scale', 'iris', 'cars', 'diabetes', 'breast-cancer',
                          'glass2', 'glass', 'breast', 'solar', 'cleve', 'hepatitis'],
               'big' : ['heart', 'australian', 'crx', 'german', 'german-org', 'auto',
                        'anneal-U']}

DATAFOLDER = os.path.join(wmibench_path, 'data/uci-datasets')


def read_feats(path):
    feats = []
    with open(path, 'r') as f:
        for line in f:
            if len(line) == 0:
                continue

            tokens = line.strip()[:-1].split(':')
            assert(len(tokens) > 0), "Couldn't parse any token"

            feat_name = "".join(c for c in tokens[0] if c in ascii_letters + '0123456789')
            str_type = tokens[1]                
                
            if str_type == "continuous" or str_type == "discrete":
                feats.append(Symbol(feat_name, REAL))

            elif str_type == "categorical":
                nvals = len(tokens[2].split(","))
                if nvals == 2:
                    feats.append(Symbol(feat_name, BOOL))
                else:
                    for i in range(nvals):
                        feats.append(Symbol(f'{feat_name}_OHE_{i}', BOOL))
            else:
                print("Unsupported feature type: {str_type}")
                exit(1)

    return feats


def read_data(path, feats):
    data = []
    with open(path, 'r') as f:
        for line in f:
            if len(line) == 0:
                continue

            tokens = line[:-1].replace(' ','').split(',')                
            row = []
            i = 0
            for token in tokens:
                if 'OHE' not in feats[i].symbol_name():
                    if feats[i].symbol_type() == BOOL:
                        assert(token in ["0", "1"])
                        row.append(bool(int(token)))
                    else:
                        row.append(float(token))

                    i += 1

                else:
                    prefix = "_".join(
                        feats[i].symbol_name().split("_")[:-1])
                    cardinality = len([f for f in feats if prefix in
                                       f.symbol_name()])
                    assert(int(float(token)) < cardinality)
                    subrow = [False for _ in range(cardinality)]
                    subrow[int(float(token))] = True
                    row.extend(subrow)
                    i += cardinality

                data.append(row)

    return np.array(data)

def uci_latex_table():
    ''' Generates a LaTeX table with statistics on the dataset.'''
    
    rows = ['\\hline', 'Dataset & $|\\allA|$ & $|\\allX|$ & \\# Train & \\# Valid\\\\', '\\hline']
    for size in EXPERIMENTS:
        for exp in EXPERIMENTS[size]:
            featfile = os.path.join(DATAFOLDER, f'{exp}.features')
            feats = read_feats(featfile)
            train = read_data(os.path.join(DATAFOLDER, f'{exp}.train.data'), feats)
            valid = read_data(os.path.join(DATAFOLDER, f'{exp}.valid.data'), feats)
            nbools = len([v for v in feats if v.symbol_type() == BOOL])
            nreals = len([v for v in feats if v.symbol_type() == REAL])
            rows.append(f'{exp} & {nbools} & {nreals} & {len(train)} & {len(valid)} \\\\')

    with open('table.tex', 'w') as f:
        f.write('\n'.join(rows))

def generate_uci_loop(root_folder, uci_to_pywmi):

    for size in EXPERIMENTS:
        benchmark_folder = os.path.join(root_folder, f'{size}')

        if not os.path.isdir(benchmark_folder):
            os.mkdir(benchmark_folder)

        for exp in EXPERIMENTS[size]:
            # fresh pysmt environment
            reset_env()
    
            detfile = os.path.join(benchmark_folder, f'{exp}.json')

            if os.path.isfile(detfile):
                print(f"{detfile} exists. Skipping.")
                continue

            print(f"{exp} : Parsing data")
            featfile = os.path.join(DATAFOLDER, f'{exp}.features')
            feats = read_feats(featfile)
            train = read_data(os.path.join(DATAFOLDER, f'{exp}.train.data'), feats)
            valid = read_data(os.path.join(DATAFOLDER, f'{exp}.valid.data'), feats)
            print(f"{exp} : Training model & generating queries")                        
            density = uci_to_pywmi(feats, train, valid)
            density.to_file(detfile)  # Save to file    
