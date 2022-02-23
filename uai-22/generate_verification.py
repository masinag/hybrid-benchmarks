
from det import DET
from itertools import product as prod
import matplotlib.pyplot as plt
import numpy as np
import numpy.random as rng
import os
from pysmt.shortcuts import *
from pywmi import Density
from relu import Dataset, ReluNet
from scipy.linalg import solve as solve_linear_system
import torch
from torch.utils.data import DataLoader

def plot_losses(train_loss, test_loss, title="", ylabel="Loss", path=None):
    xs = range(1,len(train_loss)+1)
    fig, ax = plt.subplots()
    plt.title(title)
    plt.xlabel('Epoch')
    plt.ylabel(ylabel)    
    ax.plot(xs, train_loss, label=f"Training set", color='blue')
    ax.plot(xs, test_loss, label=f"Test set", color='green')
    ax.legend()

    if path is not None:
        plt.savefig(path)

    plt.show()
    plt.clf()



def sample_from_prior(probcl, meancl, stdcl, nsamples, seed):
    '''Samples 'nsamples' points from the mixture of Gaussians: 

    (probcl, meancl, stdcl)

    '''
    assert(len(probcl) == len(meancl))
    assert(len(probcl) == len(stdcl))
    rng.seed(seed)
    samples = []
    for cl in rng.choice(len(probcl), nsamples, p=probcl):
        samples.append(rng.normal(meancl[cl], stdcl[cl]))

    return np.array(samples)

def train(dataloader, model, loss_fn, optimizer, device="cpu"):
    train_loss = 0
    i = 0
    for X, y in dataloader:
        
        X, y = X.to(device), y.to(device)

        # Compute prediction error
        pred = model(X)
        loss = loss_fn(pred, y)

        train_loss += loss.item()
        i += 1

        # Backpropagation
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()


    train_loss /= len(dataloader)
    return train_loss


def test(dataloader, model, loss_fn, device="cpu"):
    model.eval()
    test_loss = 0
    with torch.no_grad():
        for X, y in dataloader:
            X, y = X.to(device), y.to(device)
            pred = model(X)
            test_loss += loss_fn(pred, y).item()

    test_loss /= len(dataloader)
    return test_loss


def run(train_dataloader, test_dataloader, max_epochs, model, loss_fn,
        optimizer, device):

    train_loss, test_loss = [], []
    for t in range(max_epochs):
        train_l = train(train_dataloader, model, loss_fn, optimizer, device)
        test_l = test(test_dataloader, model, loss_fn, device)        
        train_loss.append(train_l)
        test_loss.append(test_l)
        if t % (max_epochs / 100) == 0:
            print(f"Epoch {t+1}\n-------------------------------")
            print("Train loss", train_l)
            print("Test loss", test_l)

    return train_loss, test_loss



if __name__ == '__main__':

    seed = 666

    # problem
    xdim = 3
    ydim = 1
    ncl = 3
    epsilon = 1e-2
    nhyper = 2


    benchmark_folder = f"pfv-{xdim}-{ydim}-{ncl}-{nhyper}"
    if not os.path.isdir(benchmark_folder):
        os.mkdir(benchmark_folder)

    rng.seed(seed)
    print()
    print("--------------------------------------------------")
    print("Generating ground truth")
    print("with:")
    print(f" Input dim - {xdim}\n Output dim - {ydim}")
    print(f" N. modes - {ncl}\n N. weighted halfspaces - {nhyper}")
    print()
    
    wcl = rng.uniform(size=ncl)
    probcl = wcl/np.sum(wcl)
    meancl = [rng.uniform(-1, +1, size=xdim) for _ in range(ncl)]
    stdcl = [rng.uniform(0, 1, size=xdim) for _ in range(ncl)]

    constraints = []
    for i in range(nhyper):
        bbox = [(-1, +1) for _ in range(xdim)]
        p = np.array([np.random.uniform(l, u) for l, u in bbox])
        # uniformly sampled orientation for the hyperplane
        o = np.random.uniform(0, 1, (xdim-1, xdim))
        # coefficients for the system of equations (i.e. n points in ndimensions)
        Points = p * np.concatenate((np.ones((1, xdim)), o))
        
        # solving the system to retrieve the hyperplane's coefficients
        # [p1 ; ... , pn] * coeffs = 1
        w = solve_linear_system(Points, np.ones((xdim, 1))).transpose()[0]
        lincomb = rng.uniform(size=(xdim, ydim))
        constraints.append((w, lincomb))
    
    # relunet
    hiddendim = 32 #32
    reludim = (xdim, hiddendim, ydim)
    nn_trainsize = 10000
    nn_testsize = 1000
    nepochs = 1000
    batch_size = 100
    lr = 1e-3
    loss = torch.nn.MSELoss()
    threshold = 0.0

    dimstr = str(reludim).replace(' ','')
    nnstr = f'model-{dimstr}-{nn_trainsize}-{nepochs}-{batch_size}-{lr}'
    relupath = os.path.join(benchmark_folder, nnstr + '.pth')

    relunet = ReluNet(reludim, seed)
    print("--------------------------------------------------")
    print("Training the Relunet")
    print("with:")
    print(f" Size - {dimstr}\n Epochs - {nepochs}")
    print(f" Training data - {nn_trainsize}\n Batch size - {batch_size}")
    print(f" Learning rate - {lr}")
    print()

    if os.path.isfile(relupath):
        print("Found model:", relupath)
        print()
        relunet.load_state_dict(torch.load(relupath))
    else:
        # sampling Xt ~ P*(X)
        sample = sample_from_prior(probcl, meancl, stdcl,
                                   nn_trainsize + nn_testsize, seed)

        #labelling Yt = Xt * c
        train_x = sample[:nn_trainsize]
        test_x = sample[nn_trainsize:]
    
        train_y = []
        for x in train_x:
            c = np.ones((xdim, ydim))
            #constraints = rng.uniform(size=(xdim, ydim))
            for w, lc in constraints:
                if np.matmul(x, w) <= 1:
                    c *= lc
                
            y = np.matmul(x, c)
            train_y.append(y)
        
        test_y = []
        for x in test_x:
            c = np.ones((xdim, ydim))
            #constraints = rng.uniform(size=(xdim, ydim))
            for w, lc in constraints:
                if np.matmul(x, w) <= 1:
                    c *= lc
                
            y = np.matmul(x, c)
            test_y.append(y)

        def seed_worker(worker_id):
            worker_seed = torch.initial_seed() % 2**32
            rng.seed(worker_seed)
            random.seed(worker_seed) # dunno

        g = torch.Generator()
        g.manual_seed(0)

        train_dl = DataLoader(Dataset(train_x, train_y),
                              batch_size=batch_size,
                              worker_init_fn=seed_worker,
                              generator=g)
        test_dl = DataLoader(Dataset(test_x, test_y),
                             batch_size=batch_size,
                             worker_init_fn=seed_worker,
                             generator=g)
    
        device = "cuda" if torch.cuda.is_available() else "cpu"
        device = 'cpu'
        optimizer = torch.optim.SGD(relunet.parameters(), lr=lr)    
        train_loss, test_loss = run(train_dl,
                                    test_dl,
                                    nepochs,
                                    relunet,
                                    loss,
                                    optimizer,
                                    device)

        torch.save(relunet.state_dict(), relupath)
        plotpath = os.path.join(benchmark_folder, nnstr + '.png')
        plot_losses(train_loss, test_loss, path=plotpath)

    # Estimating P*(X)
    nmin = 10
    nmax = 50
    det_train = 1000
    det_valid = 100
    detstr = f'det-{nmin}-{nmax}-{det_train}-{det_valid}'

    print("--------------------------------------------------")
    print('Estimating P*(X) with DET trained on Xe ~ P*(X)')
    print("with:")
    print(f" Min. leaf size - {nmin}\n Max. leaf size - {nmax}")
    print(f" Training data - {det_train}\n Validation data - {det_valid}")
    print()

    densitystr = f'density_{nnstr}_{detstr}'
    densitypath = os.path.join(benchmark_folder, densitystr + '.json')

    if os.path.isfile(densitypath):
        print("Found density:", densitypath)
        print()
        density = Density.from_file(densitypath)
    else:
        # fitting a model on a unlabelled dataset
        det_data = sample_from_prior(probcl, meancl, stdcl,
                                     det_train + det_valid, seed+1)
        smt_relu = relunet.to_smt(threshold)
        feats = relunet.input_vars
        det = DET(feats, nmin, nmax)
        det.grow_full_tree(det_data[:det_train])
        det.prune_with_validation(det_data[det_train:])

        # encode the trained NN and DET in SMT
        domain, smt_det, weight_det = det.to_pywmi()    
        queries = []
        for mu in prod(*[[True, False] for _ in range(nhyper)]):
            cond = []
            lincomb = np.ones((xdim, ydim))
            for w, lc in constraints:

                h_smt = Plus(*[Times(Real(float(w[j])), xj)
                               for j,xj in enumerate(relunet.input_vars)])

                c_smt = LE(h_smt, Real(1))

                if mu[i]:
                    lincomb *= lc
                else:
                    c_smt = Not(c_smt)
                
                cond.append(c_smt)

            for i, yi in enumerate(relunet.output_vars):
                ci = lincomb[:,i]
                wc = Plus(*[Times(Real(float(ci[j])), xj)
                            for j,xj in enumerate(relunet.input_vars)])
                lower = LE(Plus(yi, Real(epsilon)), wc)
                upper = LE(wc, Minus(yi, Real(epsilon)))
                queries.append(And(*cond, lower, upper))
    
        density = Density(domain,
                          And(smt_relu, smt_det),
                          weight_det,
                          queries)
        density.to_file(densitypath)  # Save to file
    
