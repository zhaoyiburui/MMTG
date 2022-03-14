'''
Author: Aman
Date: 2021-11-15 10:40:56
Contact: cq335955781@gmail.com
LastEditors: Aman
LastEditTime: 2021-12-03 02:07:58
'''

import torch
import torch.nn as nn
import torch.nn.init as init
import random
import math
import numpy as np

class MultiModalEncoder(nn.Module):
    def __init__(self, model_cfgs):
        super(MultiModalEncoder, self).__init__()
        self.dropout_rate = model_cfgs['dropout']
        self.topic_input_dim = model_cfgs['topic']['input_dim']
        self.topic_hidden_dim = model_cfgs['topic']['hidden_dim']
        self.image_input_dim = model_cfgs['image']['input_dim']
        self.image_hidden_dim = model_cfgs['image']['hidden_dim']
        self.image_num_layers = model_cfgs['image']['num_layers']
        self.text_input_dim = model_cfgs['text']['input_dim']
        self.text_hidden_dim = model_cfgs['text']['hidden_dim']
        self.text_num_layers = model_cfgs['text']['num_layers']
        assert self.topic_hidden_dim == self.image_hidden_dim == self.text_hidden_dim, \
            "The hidden dim of topic, image and text must be equal."
        # for topic mlp
        self.topic_fc = nn.Linear(self.topic_input_dim, self.topic_hidden_dim)
        # for image multi-layer rnns
        if model_cfgs['image']['type'] == 'RNN':
            self.rnns_image = nn.RNN(self.image_input_dim, self.image_hidden_dim, \
                                    num_layers=self.image_num_layers, nonlinearity = "relu", dropout=self.dropout_rate)
        elif model_cfgs['image']['type'] == 'LSTM':
            self.rnns_image = nn.LSTM(self.image_input_dim, self.image_hidden_dim, \
                                    num_layers=self.image_num_layers, dropout=self.dropout_rate)
        elif model_cfgs['image']['type'] == 'GRU':
            self.rnns_image = nn.GRU(self.image_input_dim, self.image_hidden_dim, \
                                    num_layers=self.image_num_layers, dropout=self.dropout_rate)
        # for text multi-layer rnns
        if model_cfgs['text']['type'] == 'RNN':
            self.rnns_text = nn.RNN(self.text_input_dim, self.text_hidden_dim, \
                                    num_layers=self.text_num_layers, nonlinearity = "relu", dropout=self.dropout_rate)
        elif model_cfgs['text']['type'] == 'LSTM':
            self.rnns_text = nn.LSTM(self.text_input_dim, self.text_hidden_dim, \
                                    num_layers=self.text_num_layers, dropout=self.dropout_rate)
        elif model_cfgs['text']['type'] == 'GRU':
            self.rnns_text = nn.GRU(self.text_input_dim, self.text_hidden_dim, \
                                    num_layers=self.text_num_layers, dropout=self.dropout_rate)
        
        self.dropout = nn.Dropout(self.dropout_rate)
        self.init_weights()

    def forward(self, encoder_batch):
        '''
        Args:
            encoder_batch: {'topic': [seq_len, batch_size, topic_input_dim], 
                            'image': [seq_len, batch_size, input_dim]
                            'text': [seq_len, batch_size, input_dim]}
        '''
        self.rnns_image.flatten_parameters()
        self.rnns_text.flatten_parameters()
        # Inputs
        x_topic = encoder_batch['topic']
        x_image = encoder_batch['image']
        x_text = encoder_batch['text']

        # Outputs: [seq_len, batch_size, hidden_dim], hidden = [num_layers, batch_size, hidden_dim]
        output_topic = self.topic_fc(x_topic).unsqueeze(0) # [batch_size, topic_input_dim] -> [1, batch_size, topic_hidden_dim]
        output_image, hidden_image = self.rnns_image(x_image) # [seq_len, batch_size, image_input_dim] -> [seq_len, batch_size, image_hidden_dim]
        output_text, hidden_text = self.rnns_text(x_text) # [seq_len, batch_size, text_input_dim] -> [seq_len, batch_size, text_hidden_dim]

        return output_topic, output_image, output_text

    def init_weights(self):
        init.xavier_normal_(self.topic_fc.weight)
        init.xavier_normal_(self.rnns_image.weight_ih_l0)
        init.orthogonal_(self.rnns_image.weight_hh_l0)
        init.xavier_normal_(self.rnns_text.weight_ih_l0)
        init.orthogonal_(self.rnns_text.weight_hh_l0)


class MultiModalAttentionLayer(nn.Module):
    def __init__(self, model_cfgs):
        '''
        Using topic input as query to compute the weighted sum of each time step of image and text modality.
        '''
        super(MultiModalAttentionLayer, self).__init__()
        self.seq_len = model_cfgs['seq_len']
        self.dropout_rate = model_cfgs['dropout']
        self.topic_hidden_dim = model_cfgs['topic']['hidden_dim']
        self.image_hidden_dim = model_cfgs['image']['hidden_dim']
        self.text_hidden_dim = model_cfgs['text']['hidden_dim']
        self.attention_dim = model_cfgs['MM_ATT']['attention_dim']
        assert self.topic_hidden_dim == self.image_hidden_dim == self.text_hidden_dim # should be equal
        self.att_input_dim = self.topic_hidden_dim

        # topic as query
        self.topic_q = nn.Linear(self.att_input_dim, self.attention_dim)
        # self.k = nn.ModuleList([nn.Linear(self.att_input_dim, self.attention_dim) for i in range(self.seq_len)])
        self.v = nn.ModuleList([nn.Linear(self.att_input_dim, self.attention_dim) for i in range(self.seq_len)])
        self._norm_fact = 1 / math.sqrt(self.attention_dim)

    def forward(self, topic_output, image_output, text_output):
        '''
        Args:
            topic_output: [1, batch_size, hidden_dim]
            image_output, text_output: [seq_len, batch_size, hidden_dim]
        '''
        Q = self.topic_q(topic_output).transpose(0, 1) # Q: [batch_size, 1, attention_dim]
        batch_size = image_output.size(1)
        device = image_output.device
        # Attention
        atten_outputs = torch.zeros(self.seq_len, batch_size, self.attention_dim).to(device)
        for i in range(self.seq_len):
            atten_input = torch.cat([topic_output, image_output[i,:,:].unsqueeze(0), text_output[i,:,:].unsqueeze(0)], dim=0) # [3, batch_size, hidden_dim]
            V = self.v[i](atten_input).transpose(0, 1) # [3, batch_size, hidden_dim] => [batch_size, 3, attention_dim]
            atten = nn.Softmax(dim=-1)(torch.bmm(Q, V.permute(0,2,1)) * self._norm_fact) # [batch_size, 1, attention_dim] * [batch_size, attention_dim, 3] => [batch_size, 1, 3]
            output = torch.bmm(atten, V) # [batch_size, 1, 3] * [batch_size, 3, attention_dim] => [batch_size, 1, attention_dim]
            atten_outputs[i,:,:] = output.transpose(0, 1) # [batch_size, 1, attention_dim] => [1, batch_size, attention_dim]
        
        return atten_outputs # [seq_len, batch_size, attention_dim]


class SelfAttentionLayer(nn.Module):
    def __init__(self, model_cfgs):
        '''
        Compute the self attention of the hidden states of the topic, image and text inputs.
        '''
        super(SelfAttentionLayer, self).__init__()
        self.hidden_size = model_cfgs['SELF_ATT']['hidden_size']
        self.attention_heads = model_cfgs['SELF_ATT']['attention_heads']
        self.dropout_rate = model_cfgs['dropout']
        assert self.hidden_size == model_cfgs['MM_ATT']['attention_dim'] # should be equal

        if self.hidden_size % self.attention_heads != 0:
            raise ValueError("The hidden size (%d) is not a multiple of the number of attention heads (%d)" % (self.hidden_size, self.attention_heads))

        self.attention_heads = self.attention_heads
        self.attention_head_size = self.hidden_size // self.attention_heads
        self.all_head_size = int(self.attention_heads * self.attention_head_size) # all_head_size = hidden_size
        
        self.query = nn.Linear(self.hidden_size, self.all_head_size)
        self.key = nn.Linear(self.hidden_size, self.all_head_size)
        self.value = nn.Linear(self.hidden_size, self.all_head_size)
        
        # dropout
        self.dropout = nn.Dropout(self.dropout_rate)

    def reshape_for_scores(self, x):
        '''
        Reshape the weight matrix to multi-heads form.
        Args:
            x: [bs, 3, hid_size]
        '''
        new_x_shape = x.size()[:-1] + (self.attention_heads, self.attention_head_size) # [bs, 3, attention_heads, attention_head_size]
        x = x.view(*new_x_shape)
        return x.permute(0, 2, 1, 3) # [bs, attention_heads, 3, attention_head_size]

    def forward(self, mm_attention_output):
        '''
        Args:
            mm_attention_output: [batch_size, seq_len, attention_dim]
        '''
        mixed_query_layer = self.query(mm_attention_output)
        mixed_key_layer = self.key(mm_attention_output)
        mixed_value_layer = self.value(mm_attention_output) # [bs, seq_len, hidden_size]

        query_layer = self.reshape_for_scores(mixed_query_layer)
        key_layer = self.reshape_for_scores(mixed_key_layer)
        value_layer = self.reshape_for_scores(mixed_value_layer) # [bs, attention_heads, seq_len, attention_head_size]

        attention_scores = torch.matmul(query_layer, key_layer.transpose(-1, -2)) # [bs, attention_heads, seq_len, seq_len]
        attention_scores = attention_scores / math.sqrt(self.attention_head_size) # [bs, attention_heads, seq_len, seq_len]

        attention_probs = nn.Softmax(dim=-1)(attention_scores) # [bs, attention_heads, seq_len, seq_len]

        attention_probs = self.dropout(attention_probs)
        
        # [bs, attention_heads, seq_len, seq_len] * [bs, attention_heads, seq_len, attention_head_size] = [bs, attention_heads, seq_len, attention_head_size]
        context_layer = torch.matmul(attention_probs, value_layer) # [bs, attention_heads, seq_len, attention_head_size]
        context_layer = context_layer.permute(0, 2, 1, 3).contiguous() # [bs, seq_len, attention_heads, attention_head_size]
        new_context_layer_shape = context_layer.size()[:-2] + (self.all_head_size,) # [bs, seq_len, out_hidden_size]
        context_layer = context_layer.view(*new_context_layer_shape)

        return context_layer # [bs, seq_len, out_hidden_size]


class AggregateLayer(nn.Module):
    def __init__(self, model_cfgs):
        '''
        Aggregate the attention outputs.
        '''
        super(AggregateLayer, self).__init__()
        self.type = model_cfgs['agg']['type']
        self.input_dim = model_cfgs['SELF_ATT']['hidden_size']
        self.output_dim = model_cfgs['agg']['output_dim']
        self.agg_num_layers = model_cfgs['agg']['num_layers']
        self.dropout_rate = model_cfgs['dropout']

        # for aggregate multi-layer rnns
        if model_cfgs['agg']['type'] == 'RNN':
            self.agg_layer = nn.RNN(self.input_dim, self.output_dim, num_layers=self.agg_num_layers, nonlinearity = "relu", dropout=self.dropout_rate)
        elif model_cfgs['agg']['type'] == 'LSTM':
            self.agg_layer = nn.LSTM(self.input_dim, self.output_dim, num_layers=self.agg_num_layers, dropout=self.dropout_rate)
        elif model_cfgs['agg']['type'] == 'GRU':
            self.agg_layer = nn.GRU(self.input_dim, self.output_dim, num_layers=self.agg_num_layers, dropout=self.dropout_rate)
        
        self.init_weights()

    def forward(self, input):
        '''
        Args:
            input (self_attention_output): [seq_len, bs, attention_dim]
        '''
        self.agg_layer.flatten_parameters()
        output_agg, hidden_agg = self.agg_layer(input)
        
        return output_agg # [seq_len, batch_size, agg_output_dim]

    def init_weights(self):
        init.xavier_normal_(self.agg_layer.weight_ih_l0)
        init.orthogonal_(self.agg_layer.weight_hh_l0)


class MultiDecoders(nn.Module):
    def __init__(self, model_cfgs, vocab_size):
        super(MultiDecoders, self).__init__()
        self.model_cfgs = model_cfgs
        self.dropout_rate = model_cfgs['dropout']
        self.seq_len = model_cfgs['seq_len']
        self.agg_output_dim = model_cfgs['agg']['output_dim']
        self.embedding_dim = model_cfgs['decoder']['embedding_dim']
        self.decoder_hidden_dim = model_cfgs['decoder']['hidden_dim']
        self.decoder_num_layers = model_cfgs['decoder']['num_layers']
        self.decoder_output_dim = vocab_size
        assert self.decoder_hidden_dim == self.agg_output_dim, \
            "The hidden dim of decoder must be equal to the hidden dim of agg layer"

        # embedding layer
        self.embeddings = nn.Embedding(vocab_size, self.embedding_dim)
        # for decoder multi-layer rnns
        if self.model_cfgs['decoder']['type'] == 'RNN':
            self.decoders = nn.ModuleList([nn.RNN(self.agg_output_dim + self.embedding_dim, self.decoder_hidden_dim, num_layers=self.decoder_num_layers, \
                                          nonlinearity = "relu", dropout=self.dropout_rate) for i in range(self.seq_len)])
        elif self.model_cfgs['decoder']['type'] == 'LSTM':
            self.decoders = nn.ModuleList([nn.LSTM(self.agg_output_dim + self.embedding_dim, self.decoder_hidden_dim, num_layers=self.decoder_num_layers, \
                                          dropout=self.dropout_rate) for i in range(self.seq_len)])
        elif self.model_cfgs['decoder']['type'] == 'GRU':
            self.decoders = nn.ModuleList([nn.GRU(self.agg_output_dim + self.embedding_dim, self.decoder_hidden_dim, num_layers=self.decoder_num_layers, \
                                          dropout=self.dropout_rate) for i in range(self.seq_len)])
            # self.decoders = nn.GRU(self.agg_output_dim + self.embedding_dim, self.decoder_hidden_dim, num_layers=self.decoder_num_layers, \
            #                               dropout=self.dropout_rate)
        else:
            raise ValueError('Decoder RNN type not supported')

        # self.fcs = nn.ModuleList([nn.Linear(self.embedding_dim + self.decoder_hidden_dim + self.agg_output_dim, self.decoder_output_dim) for i in range(self.seq_len)])
        self.fcs = nn.Linear(self.embedding_dim + self.decoder_hidden_dim + self.agg_output_dim, self.decoder_output_dim)
        self.dropouts = nn.ModuleList([nn.Dropout(self.dropout_rate) for i in range(self.seq_len)])
        # self.init_weights()

    def forward(self, input, hidden, output_agg, teacher_forcing_ratio):
        '''
        Args:
            input: [batch_size, seq_len, _max_sent_length*2]
            hidden: [seq_len, batch_size, agg_output_dim]
            output_agg (context): [seq_len, batch_size, agg_output_dim]
        '''
        for i in range(self.seq_len):
            self.decoders[i].flatten_parameters()
        batch_size, seq_len, output_len = input.size()
        input = input.transpose(0, 1) # [seq_len, batch_size, _max_sent_length*2]
        device = input.device
        
        outputs = torch.zeros(seq_len, output_len, batch_size, self.decoder_output_dim).to(device)
        for i in range(seq_len):
            decoder_input = input[i,:,0] # [batch_size]
            decoder_hidden = hidden[i,:,:].unsqueeze(0) # [1, batch_size, decoder_hidden_dim]
            output_agg_line = output_agg[i,:,:].unsqueeze(0) # [1, batch_size, agg_output_dim]
            if i == 0:
                ctx_hidden_state = output_agg_line
            else: # 层次间的信息传递
                ctx_hidden_state = decoder_hidden
            line_outputs = torch.zeros(output_len, batch_size, self.decoder_output_dim).to(device)
            line_outputs[0, :, 1] = 1

            for j in range(1, output_len):
                # Embedding
                embedded = self.dropouts[i](self.embeddings(decoder_input)).unsqueeze(0) # [1, batch_size, embedding_dim]
                # Concatenate
                embedded_agg = torch.cat((embedded, ctx_hidden_state), dim = 2) # [1, batch_size, embedding_dim + agg_output_dim]
                # RNN
                decoder_output, decoder_hidden = self.decoders[i](embedded_agg, decoder_hidden) # decoder_output: [batch_size, vocab_size], hidden: [1, batch_size, hidden_dim]
                # Dropout
                # decoder_output = self.dropouts[i](decoder_output)
                decoder_output = torch.cat((embedded.squeeze(0), decoder_hidden.squeeze(0), output_agg_line.squeeze(0)), dim = 1)
                # Linear
                logits = self.fcs(decoder_output) # [batch_size, vocab_size]
                teacher_force = random.random() < teacher_forcing_ratio
                topv, topi = logits.topk(1) # values, indices
                decoder_input = (input[i,:,j] if teacher_force else topi.view(-1))
                line_outputs[j] = logits
            outputs[i] = line_outputs

        return outputs.permute(2, 0, 1, 3) # [batch_size, seq_len, output_len, vocab_size]
    
    # def init_weights(self):
    #     for i in range(self.seq_len):
    #         init.xavier_normal_(self.decoders[i].weight_ih_l0)
    #         init.orthogonal_(self.decoders[i].weight_hh_l0)
    #         init.xavier_normal_(self.fcs[i].weight)
    #         init.constant_(self.fcs[i].bias, 0)



class EXPTeller(nn.Module):
    def __init__(self, model_cfgs, vocab_size):
        super(EXPTeller, self).__init__()
        self.model_cfgs = model_cfgs
        self.vocab_size = vocab_size
        self.encoder = MultiModalEncoder(model_cfgs)
        self.mm_atten_layer = MultiModalAttentionLayer(model_cfgs)
        self.self_atten_layer = SelfAttentionLayer(model_cfgs)
        self.agg_layer = AggregateLayer(model_cfgs)
        self.decoder = MultiDecoders(model_cfgs, vocab_size)

    def forward(self, batch, teacher_forcing_ratio=0.5):
        '''
        Args:
            batch: {
                'topic_emb': [seq_len, batch_size, input_dim],
                'img_embs': [seq_len, batch_size, input_dim],
                'r_embs': [seq_len, batch_size, input_dim],
                'targets': [seq_len, _max_sent_length*2]
            }
        '''
        encoder_batch = {'topic': batch['topic_emb'].float(), \
                         'image': batch['img_embs'].transpose(0, 1).float(), \
                         'text': batch['r_embs'].transpose(0, 1).float()}

        # Multi-modal Encoder
        topic_output, image_output, text_output = self.encoder(encoder_batch)
        # topic_output: [1, batch_size, hidden_dim], image_output, text_output: [seq_len, batch_size, hidden_dim]
        
        # Multi-modal Attention Layer
        mm_attention_output = self.mm_atten_layer(topic_output, image_output, text_output)
        # [seq_len, batch_size, attention_dim]

        # Self Attention Layer
        self_attention_output = self.self_atten_layer(mm_attention_output.transpose(0, 1))
        # [batch_size, seq_len, attention_dim] => [batch_size, seq_len, attention_dim]

        # Aggregate
        output_agg = self.agg_layer(self_attention_output.transpose(0, 1))
        # [seq_len, batch_size, attention_dim] => [seq_len, batch_size, agg_output_dim]

        # Decoder
        decoder_hidden = output_agg
        decoder_input = batch['targets'] # [batch_size, seq_len, _max_sent_length*2]
        decoder_outputs = self.decoder(decoder_input, decoder_hidden, output_agg, teacher_forcing_ratio)
        
        return decoder_outputs # [batch_size, seq_len, output_len, vocab_size]

