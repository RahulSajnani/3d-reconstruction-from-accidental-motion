'''
This module creates a dense reconstruction of the 3D Scene from the sparse 3D points
estimated from the bundle adjustment module. It initializes a CRF model based on the
sparse points and the input RGB image.
'''

import os
import cv2
import config
import argparse
import numpy as np
from plane_sweep import plane_sweep
from pydensecrf import densecrf as dcrf
from pydensecrf.utils import create_pairwise_bilateral, unary_from_softmax

def compute_unary_image(unary, depth_samples, outfile):

	gd = np.argmin(unary, axis=0)
	gd_im = np.zeros((unary.shape[1], unary.shape[2]))
	for i in range(unary.shape[1]):
		for j in range(unary.shape[2]):
			gd_im[i,j] = (((depth_samples[gd[i,j]] - depth_samples[-1]) * 255) / (depth_samples[0] - depth_samples[-1]) )

	cv2.imwrite(outfile, gd_im)

def DenseCRF(unary, img, depth_samples, params, outfile='depth_map.png'):

	labels = unary.shape[0]
	iters = params['iters']
	weight = params['weight']
	pos_std = params['pos_std']
	rgb_std = params['rgb_std']
	max_penalty = params['max_penalty']

	# Get initial crude depth map from photoconsistency
	# compute_unary_image(unary, depth_samples, outfile='unary.png')

	# Normalize values for each pixel location
	for r in range(unary.shape[1]):
		for c in range(unary.shape[2]):
			if np.sum(unary[:, r, c]) <= 1e-9:
				unary[:, r, c] = 0.0
			else:
				unary[:, r, c] = (unary[:, r, c]/np.sum(unary[:, r, c]))

	# Convert to class probabilities for each pixel location
	unary = unary_from_softmax(unary)
	d = dcrf.DenseCRF2D(img.shape[1], img.shape[0], labels)

	# Add photoconsistency score as uanry potential. 16-size vector
	# for each pixel location
	d.setUnaryEnergy(unary)
	# Add color-dependent term, i.e. features are (x,y,r,g,b)
	d.addPairwiseBilateral(sxy=pos_std, srgb=rgb_std, rgbim=img, compat=np.array([weight, labels*max_penalty]), kernel=dcrf.DIAG_KERNEL, normalization=dcrf.NORMALIZE_SYMMETRIC)

	# Run inference steps
	Q = d.inference(iters)

	# Extract depth values. Map to [0-255]
	MAP = np.argmax(Q, axis=0).reshape((img.shape[:2]))
	depth_map = np.zeros((MAP.shape[0], MAP.shape[1]))

	for i in range(MAP.shape[0]):
		for j in range(MAP.shape[1]):

			sample = depth_samples[MAP[i,j]]
			sample = (((sample - depth_samples[-1]) * 255) / (depth_samples[0] - depth_samples[-1]) )
			depth_map[i,j] = sample

	cv2.imwrite(outfile, depth_map)

def dense_depth(folder, num_samples, pc_score = None) :

	scale = config.PS_PARAMS['scale']
	max_depth = config.PS_PARAMS['max_depth']
	min_depth = config.PS_PARAMS['min_depth']
	patch_radius = config.PS_PARAMS['patch_radius']


	# Create depth samples in the specified depth range
	depth_samples = np.zeros(num_samples)
	step = step = 1.0 / (num_samples - 1.0)

	for val in range(num_samples):
		sample = (max_depth * min_depth) / (max_depth - (max_depth - min_depth) * val * step)
		# Can use fx = 1781.0
		depth_samples[val] = config.CAMERA_PARAMS['fx']/sample

	if pc_score is None :
		# Perform plane sweep to calculate photo-consistency loss

		# TODO: Change naming convention
		outfile = f'{folder}_cost_volume_{depth_samples.shape[0]}'
		ref_image, pc_score = plane_sweep(folder, outfile, depth_samples, min_depth, max_depth, scale, patch_radius)
		print("Finished computing unary...")

	else :
		file = sorted(os.listdir(config.IMAGE_DIR.format(folder)))[0]
		ref_img = cv2.imread(os.path.join(config.IMAGE_DIR.format(folder), file))
		ref_img = cv2.cvtColor(ref_img, cv2.COLOR_BGR2RGB)
		for s in range(scale):
			ref_img = cv2.pyrDown(ref_img)

	outfile = 'depth_map.png'
	# Use photoconsistency score as unary potential
	depth_map = DenseCRF(pc_score, ref_img, depth_samples, config.CRF_PARAMS, outfile)
	print("Finished solving CRF...")


parser = argparse.ArgumentParser()
parser.add_argument("--folder", help='Folder in dataset dir', default='stone6', required=True)
parser.add_argument("--nsamples", help='Number of depth samples', default=16, required=True)
args = parser.parse_args()

# pc = np.load('cost_volume_16_5.npy')
dense_depth(args.folder, int(args.nsamples))
