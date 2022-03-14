'''
Author: Aman
Date: 2021-11-15 11:13:35
Contact: cq335955781@gmail.com
LastEditors: Aman
LastEditTime: 2021-12-14 01:36:49
'''


# type: [str], RNN type
# input_dim: [int], input dimension
# hidden_dim: [int], hidden dimension
# seq_dim: [int], number of cells per layer
# num_layers: [int], number of layers
model_cfgs = {
    'seq_len': 5,
    'topic': {
        'input_dim': 2048,
        'hidden_dim': 512
    },
    'image': {
        'type': 'GRU',
        'input_dim': 2048,
        'hidden_dim': 512,
        'num_layers': 1
    },
    'text': {
        'type': 'GRU',
        'input_dim': 2048,
        'hidden_dim': 512, 
        'num_layers': 1
    },
    'SELF_ATT': {
        'hidden_size': 512, # topic, image, text and self att hidden dims must be equal
        'attention_heads': 4
    },
    'MM_ATT': {
        'attention_dim': 1024
    },
    'agg': {
        'type': 'GRU',
        'output_dim': 2048,
        'num_layers': 1
    },
    'decoder': {
        'type': 'GRU',
        'hidden_dim': 512, # equals with agg.output_dim
        'num_layers': 1,
        'embedding_dim': 512
    },
    'GPT2_PATH': '/home/caoqian/playground/GPT2-Chinese-master/5ep_tsteps5w/last.ckpt',
    'dropout': 0.2
}

class data_config():
    def __init__(self):
        self.max_sent_length = 20
        # self.max_seq_length = 150

