#AUTOGENERATED! DO NOT EDIT! File to edit: dev/34_callback_rnn.ipynb (unless otherwise specified).

__all__ = ['RNNTrainer']

#Cell
from ..test import *
from ..data.all import *
from ..optimizer import *
from ..learner import *

#Cell
@docs
class RNNTrainer(Callback):
    "`Callback` that adds AR and TAR regularization in RNN training"
    def __init__(self, alpha=0., beta=0.): self.alpha,self.beta = alpha,beta

    def begin_train(self):    self.model.reset()
    def begin_validate(self): self.model.reset()
    def after_pred(self):
        self.raw_out,self.out = self.pred[1],self.pred[2]
        self.learn.pred = self.pred[0]

    def after_loss(self):
        if not self.training: return
        if self.alpha != 0.:  self.learn.loss += self.alpha * self.out[-1].float().pow(2).mean()
        if self.beta != 0.:
            h = self.raw_out[-1]
            if len(h)>1: self.learn.loss += self.beta * (h[:,1:] - h[:,:-1]).float().pow(2).mean()

    _docs = dict(begin_train="Reset the model before training",
                begin_validate="Reset the model before validation",
                after_pred="Save the raw and dropped-out outputs and only keep the true output for loss computation",
                after_loss="Add AR and TAR regularization")
