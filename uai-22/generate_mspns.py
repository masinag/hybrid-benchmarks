
import numpy as np
import os
from pysmt.shortcuts import *
from pywmi import Density, Domain
from scipy.linalg import solve as solve_linear_system
from spn.structure.Base import Context
from spn.structure.Base import Sum, Product
from spn.structure.StatisticalTypes import MetaType
from spn.algorithms.LearningWrappers import learn_mspn
from sys import argv
from utils import read_feats, read_data



def recw(node):
    if isinstance(node, Sum):
        return Plus(*[Times(Real(node.weights[i]), recw(c))
                      for i,c in enumerate(node.children)])
    elif isinstance(node, Product):
        return Times(*[recw(c) for c in node.children])
    else:
        assert(len(node.scope) == 1)
        var = feats[node.scope[0]]
        if var.symbol_type() == BOOL:
            assert(len(node.densities) == 2)
            ite = Ite(var,
                      Real(node.densities[1]),
                      Real(node.densities[0]))
        else:
            intervals = [And(LE(Real(node.breaks[i]), var),
                             LT(var, Real(node.breaks[i+1])))
                         for i in range(len(node.densities))]
            ite = Ite(intervals[0],
                      Real(node.densities[0]),
                      Real(1-sum(node.densities)))
            for i in range(1, len(intervals)):
                ite = Ite(intervals[i],
                          Real(node.densities[i]),
                          ite)
        return ite


# full MLC suite sorted by increasing number of features
EXPERIMENTS = {'small' : ['balance-scale', 'iris', 'cars', 'diabetes', 'breast-cancer',
                          'glass2', 'glass', 'breast', 'solar', 'cleve', 'hepatitis'],
               'big' : ['heart', 'australian', 'crx', 'german', 'german-org', 'auto',
                        'anneal-U']}

DATAFOLDER = 'mlc-datasets'



if len(argv) != 5:
    print("Usage: python3 generate_mspns.py MIN_INSTANCE_SLICES NQUERIES QUERYHARDNESS SEED")
    exit(1)

mininstslices, nqueries, qhardness, seed = int(argv[1]), int(argv[2]), float(argv[3]), int(argv[4])

for size in EXPERIMENTS:
    benchmark_folder = f'{size}-mspns-{mininstslices}-{nqueries}-{qhardness}-{seed}'

    if not os.path.isdir(benchmark_folder):
        os.mkdir(benchmark_folder)

    for exp in EXPERIMENTS[size]:
        # fresh pysmt environment
        reset_env()
    
        mspnfile = os.path.join(benchmark_folder, f'{exp}-{mininstslices}.json')

        if os.path.isfile(mspnfile):
            print(f"{mspnfile} exists. Skipping.")
            continue

        print(f"{exp} : Parsing data")
        featfile = os.path.join(DATAFOLDER, f'{exp}.features')
        feats = read_feats(featfile)
        train = read_data(os.path.join(DATAFOLDER, f'{exp}.train.data'), feats)
        valid = read_data(os.path.join(DATAFOLDER, f'{exp}.valid.data'), feats)

        print(f"{exp} : Learning MSPN({mininstslices})")
        mtypes = [MetaType.DISCRETE
                  if (f.symbol_type() == BOOL)
                  else MetaType.REAL
                  for f in feats]
        ds_context = Context(meta_types=mtypes)
        ds_context.add_domains(train)
        mspn = learn_mspn(train, ds_context, min_instances_slice=mininstslices)
        '''
        size = 100
        a = np.random.randint(2, size=size).reshape(-1, 1)
        b = np.random.randint(3, size=size).reshape(-1, 1)
        c = np.r_[np.random.normal(10, 5, (int(size/2), 1)), np.random.normal(20, 10, (size - int(size/2), 1))]
        d = 5 * a + 3 * b + c
        train_data = np.c_[a, b, c, d]
        ds_context = Context(meta_types=[MetaType.DISCRETE, MetaType.DISCRETE, MetaType.REAL, MetaType.REAL])
        ds_context.add_domains(train_data)
        mspn = learn_mspn(train_data,
                          ds_context,
                          min_instances_slice=mininstslices)

        print("done")
        '''
        clauses = []
        bvars = []
        cvars = []
        cbounds = []
        for i, var in enumerate(feats):
            if var.symbol_type() == REAL:
                lb, ub = ds_context.domains[i]
                cvars.append(var.symbol_name())
                cbounds.append((lb, ub))
                clauses.append(LE(Real(float(lb)), var))
                clauses.append(LE(var, Real(float(ub))))
            else:
                bvars.append(var.symbol_name())

        support = And(*clauses)
        weight = recw(mspn)
        domain = Domain.make(bvars, cvars, cbounds)
        
        queries = []
        i = 0
        np.random.seed(seed)
        while i < nqueries:
            bbox = [domain.var_domains[v] for v in domain.real_vars]
            nvars = len(bbox)
            p = np.array([np.random.uniform(l, u) for l, u in bbox])
            # uniformly sampled orientation for the hyperplane
            o = np.random.uniform(0, 1, (nvars-1, nvars))
            # coefficients for the system of equations (i.e. n points in ndimensions)
            Points = p * np.concatenate((np.ones((1, nvars)), o))

            # solving the system to retrieve the hyperplane's coefficients
            # [p1 ; ... , pn] * coeffs = 1
            w = solve_linear_system(Points, np.ones((nvars, 1))).transpose()[0]

            # consider a subset maybe?
            selected = np.random.choice(nvars, int(nvars*qhardness), replace=False)
            if len(selected) == 0:
                selected = [np.random.choice(nvars)]

            wx = [Times(Real(float(w[j])), x)
                  for j,x in enumerate(domain.get_real_symbols())
                  if j in selected]
            query = LE(Plus(*wx), Real(1))

            if is_sat(And(support, query)):
                queries.append(query)
                i += 1
            else:
                print(f"UNSAT {i+1}/{nqueries}")
            
        density = Density(domain, support, weight, queries)
        density.to_file(mspnfile)  # Save to file
        # density = Density.from_file(filename)  # Load from file




                    

    
