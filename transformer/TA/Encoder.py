#encoding: utf-8

import torch
from torch import nn
from modules.base import SelfAttn, PositionalEmb
from modules.TA import PositionwiseFF
from math import sqrt

from transformer.Encoder import Encoder as EncoderBase

# vocabulary:
#	<pad>:0
#	<sos>:1
#	<eos>:2
#	<unk>:3
#	...
# for the classier of the decoder, <sos> is omitted

class EncoderLayer(nn.Module):

	# isize: input size
	# fhsize: hidden size of PositionwiseFeedForward
	# attn_drop: dropout for MultiHeadAttention
	# num_head: number of heads in MultiHeadAttention
	# ahsize: hidden size of MultiHeadAttention

	def __init__(self, isize, fhsize=None, dropout=0.0, attn_drop=0.0, num_head=8, ahsize=None):

		super(EncoderLayer, self).__init__()

		_ahsize = isize if ahsize is None else ahsize

		_fhsize = _ahsize * 4 if fhsize is None else fhsize

		self.attn = SelfAttn(isize, _ahsize, isize, num_head, dropout=attn_drop)

		self.ff = PositionwiseFF(isize, _fhsize, dropout)

		self.layer_normer = nn.LayerNorm(isize, eps=1e-06)

		self.drop = nn.Dropout(dropout, inplace=True) if dropout > 0.0 else None

	# inputs: input of this layer (bsize, seql, isize)

	def forward(self, inputs, mask=None):

		context = self.attn(inputs, mask=mask)

		if self.drop is not None:
			context = self.drop(context)

		context = self.layer_normer(context + inputs)

		context = self.ff(context)

		return context

class Encoder(EncoderBase):

	# isize: size of word embedding
	# nwd: number of words
	# num_layer: number of encoder layers
	# fhsize: number of hidden units for PositionwiseFeedForward
	# attn_drop: dropout for MultiHeadAttention
	# num_head: number of heads in MultiHeadAttention
	# xseql: maxmimum length of sequence
	# ahsize: number of hidden units for MultiHeadAttention

	def __init__(self, isize, nwd, num_layer, fhsize=None, dropout=0.0, attn_drop=0.0, num_head=8, xseql=512, ahsize=None, norm_output=True, num_layer_dec=6):

		_ahsize = isize if ahsize is None else ahsize

		_fhsize = _ahsize * 4 if fhsize is None else fhsize

		super(Encoder, self).__init__(isize, nwd, num_layer, _fhsize, dropout, attn_drop, num_head, xseql, _ahsize, norm_output)

		self.nets = nn.ModuleList([EncoderLayer(isize, _fhsize, dropout, attn_drop, num_head, _ahsize) for i in range(num_layer)])

		self.tattn_w = nn.Parameter(torch.Tensor(num_layer + 1, num_layer_dec).uniform_(- sqrt(2.0 / (num_layer + num_layer_dec + 1)), sqrt(2.0 / (num_layer + num_layer_dec + 1))))
		self.tattn_drop = nn.Dropout(dropout) if dropout > 0.0 else None

	# inputs: (bsize, seql)
	# mask: (bsize, 1, seql), generated with:
	#	mask = inputs.eq(0).unsqueeze(1)

	def forward(self, inputs, mask=None):

		bsize, seql = inputs.size()
		out = self.wemb(inputs)
		out = out * sqrt(out.size(-1)) + self.pemb(inputs, expand=False)

		if self.drop is not None:
			out = self.drop(out)

		out = self.out_normer(out)
		outs = [out]

		for net in self.nets:
			out = net(out, mask)
			outs.append(out)

		out = torch.stack(outs, -1)

		osize = out.size()
		out = out.view(-1, osize[-1]).mm(self.tattn_w.softmax(dim=0) if self.tattn_drop is None else self.tattn_drop(self.tattn_w).softmax(dim=0))
		osize = list(osize)
		osize[-1] = -1

		return out.view(osize)