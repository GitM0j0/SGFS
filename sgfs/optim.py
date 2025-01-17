# Load required libraries
import torch
import torchvision
import math

from torch import nn
from torch.distributions import Normal

import numpy as np


class sgfs(object):
    def __init__(self,network, epsilon,lambda_, batch_size, dataset_size):
        self.network = network
        self.n = batch_size
        self.N = dataset_size
        self.epsilon =epsilon
        self.gamma = np.float(dataset_size + batch_size) / batch_size
        self.linear_layers = [m for m in self.network.modules() if isinstance (m, nn.Linear)]
        #self.lr_init = lr
        #self.lr_decayEpoch = lr_decayEpoch
        self.lambda_ = lambda_
        self.t = 1
        self.I_hat = dict()
        self.grad_mean = dict()
        #self.learning_rate = 2. / (self.gamma + (4. / epsilon))
        self.noise_factor = 2 * math.sqrt(1. / (epsilon * self.N))


        self.grads_per_element = dict()


    def element_backward(self, activations, preactivation_grads):
        # According to Goodfellow (2015)
        # https://arxiv.org/pdf/1510.01799.pdf
        for i, l in enumerate(self.linear_layers):
            G, X = preactivation_grads[i], activations[i]
            if len(G.shape) < 2:
                G = G.unsqueeze(1)

            G *= G.shape[0] # if the function is an average

            self.grads_per_element[l] = torch.bmm(G.unsqueeze(2), X.unsqueeze(1))


    def emp_fisher(self):
        for l in self.linear_layers:

            self.grad_mean[l] = self.grads_per_element[l].sum(0) / self.n
            diff_grads = self.grads_per_element[l] - self.grad_mean[l]
            scale = (self.n - 1) ** -1

            # SGFS-f update
            cov_scores = torch.einsum('bij,bkj->ik', (diff_grads, diff_grads)) * scale

            # SGFS-d update
            #cov_scores = cov_scores.mul(torch.eye(cov_scores.size(0)))

            if self.t == 1:
                self.I_hat[l] = torch.zeros(l.weight.data.size(0),l.weight.data.size(0))
            else:
                self.I_hat[l] = ((1 - 1. / self.t) * self.I_hat[l]).add((1. / self.t) * cov_scores)





    def step(self):
        for l in self.linear_layers:
            # Mini-batch updates
            # theta_(t+1) = theta_t + 2 * (gamma * I_hat + N * grad_avg(theta_t; X_t))^⁻1 * ( grad(log p(theta_t)) + N * grad_avg(theta_t) + eta_t)
            # with eta_t ~ N(0, 4 * B / eta_t)

            # According to Ahn et al. (2012): B \propto N*I_hat
            # Porbably scale problem here!!!
            # if self.t < 10:
            #     I_hat_inv = torch.eye(self.I_hat[l].size(0))
            # else:
            eps = 1e-8 * 10 ** -(self.t // 10)
            B = self.I_hat[l]
            mat = self.gamma * self.I_hat[l] + 4. * B / self.epsilon
            mat_inv = torch.inverse(mat.add(torch.eye(self.I_hat[l].size(0))))
            #mat_inv = torch.inverse(mat)

            # Cholesky factor of matrix B

            B_ch = torch.potrf(B.add(eps, torch.eye(self.I_hat[l].size(0))), upper=True)
            #B_ch = torch.potrf(B, upper=False)

            noise = (self.noise_factor * B_ch).mm(torch.randn_like(self.grad_mean[l]))

            # Update in parameter space
            update = 2. * (mat_inv).mm((self.grad_mean[l]).add_(self.lambda_ / self.N, l.weight.data).add_(noise))
            l.weight.data.add_(-update)
            #print(update)
        self.t += 1
