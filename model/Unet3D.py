import torch
import torch.nn as nn
from experiment.UnetDto import UnetDto


def crop(tensor_in, crop_as, dims=[]):
    assert len(dims) > 0, "Specify dimensions to be cropped"
    result = tensor_in
    for dim in dims:
        result = result.narrow(dim, (tensor_in.size()[dim] - crop_as.size()[dim]) // 2, crop_as.size()[dim])
    return result


class Block3x3x3(nn.Module):
    def __init__(self, n_input, n_channels):
        super(Block3x3x3, self).__init__()
        self.bn_conv_relu_2x = nn.Sequential(
            nn.BatchNorm3d(n_input),
            nn.Conv3d(n_input, n_channels, 3, stride=1, padding=0),
            nn.LeakyReLU(0.01, True),
            nn.BatchNorm3d(n_channels),
            nn.Conv3d(n_channels, n_channels, 3, stride=1, padding=0),
            nn.LeakyReLU(0.01, True)
        )

    def forward(self, input_maps):
        return self.bn_conv_relu_2x(input_maps)


class Unet3D(nn.Module):
    def __init__(self, channels=[2, 32, 64, 128, 64, 32, 128, 2], channel_dim=1, channels_crop=[2,3,4]):
        super(Unet3D, self).__init__()
        n_ch_in, ch_b1, ch_b2, ch_b3, ch_b4, ch_b5, ch_bC, n_classes = channels

        self.channel_dim = channel_dim
        self.channels_crop = channels_crop

        self.block1 = Block3x3x3(n_ch_in, ch_b1)
        self.pool12 = nn.MaxPool3d(2, 2)
        self.block2 = Block3x3x3(ch_b1, ch_b2)
        self.pool23 = nn.MaxPool3d(2, 2)
        self.block3 = Block3x3x3(ch_b2, ch_b3)

        self.upsa34 = nn.Upsample(scale_factor=2, mode='trilinear')
        self.block4 = Block3x3x3(ch_b3 + ch_b2, ch_b4)
        self.upsa45 = nn.Upsample(scale_factor=2, mode='trilinear')
        self.block5 = Block3x3x3(ch_b4 + ch_b1, ch_b5)

        self.classify = nn.Sequential(
            nn.Conv3d(ch_b5, ch_bC, 1, stride=1, padding=0),
            nn.LeakyReLU(0.01, True),
            nn.Conv3d(ch_bC, n_classes, 1, stride=1, padding=0),
            nn.Sigmoid()
        )

    def forward(self, dto: UnetDto):
        block1_result = self.block1(dto.given_variables.input_modalities)

        block2_input = self.pool12(block1_result)
        block2_result = self.block2(block2_input)

        block3_input = self.pool23(block2_result)
        block3_result = self.block3(block3_input)
        block3_unpool = self.upsa34(block3_result)

        block2_crop = crop(block2_result, block3_unpool, dims=self.channels_crop)
        block4_input = torch.cat((block3_unpool, block2_crop), dim=self.channel_dim)
        block4_result = self.block4(block4_input)
        block4_unpool = self.upsa45(block4_result)

        block1_crop = crop(block1_result, block4_unpool, dims=self.channels_crop)
        block5_input = torch.cat((block4_unpool, block1_crop), dim=self.channel_dim)
        block5_result = self.block5(block5_input)

        segmentation = self.classify(block5_result)
        dto.outputs.core = segmentation[:, 0, :, :, :].unsqueeze(1)
        dto.outputs.penu = segmentation[:, 1, :, :, :].unsqueeze(1)

        return dto