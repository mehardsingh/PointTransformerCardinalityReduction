# SOURCE: https://www.kaggle.com/code/balraj98/pointnet-for-3d-object-classification-ii-pytorch

import numpy as np
import torch
import random
import torch
from torchvision import transforms
from torch.utils.data import Dataset
import math
import os
from pathlib import Path
from tqdm import tqdm
from collections import Counter
from torch.utils.data import DataLoader, random_split

def get_pointcloud_metadata(file):
    off_header = file.readline().strip()
    if 'OFF' == off_header:
        n_verts, n_faces, __ = tuple([int(s) for s in file.readline().strip().split(' ')])
    else:
        n_verts, n_faces, __ = tuple([int(s) for s in off_header[3:].split(' ')])

    return n_verts, n_faces

def read_off(file):
    off_header = file.readline().strip()
    if 'OFF' == off_header:
        n_verts, n_faces, __ = tuple([int(s) for s in file.readline().strip().split(' ')])
    else:
        n_verts, n_faces, __ = tuple([int(s) for s in off_header[3:].split(' ')])
    verts = [[float(s) for s in file.readline().strip().split(' ')] for i_vert in range(n_verts)]
    faces = [[int(s) for s in file.readline().strip().split(' ')][1:] for i_face in range(n_faces)]
    return verts, faces

class PointSampler(object):
    def __init__(self, output_size):
        assert isinstance(output_size, int)
        self.output_size = output_size
    
    def triangle_area(self, pt1, pt2, pt3):
        side_a = np.linalg.norm(pt1 - pt2)
        side_b = np.linalg.norm(pt2 - pt3)
        side_c = np.linalg.norm(pt3 - pt1)
        s = 0.5 * ( side_a + side_b + side_c)
        return max(s * (s - side_a) * (s - side_b) * (s - side_c), 0)**0.5

    def sample_point(self, pt1, pt2, pt3):
        # barycentric coordinates on a triangle
        # https://mathworld.wolfram.com/BarycentricCoordinates.html
        s, t = sorted([random.random(), random.random()])
        f = lambda i: s * pt1[i] + (t-s)*pt2[i] + (1-t)*pt3[i]
        return (f(0), f(1), f(2))
        
    
    def __call__(self, mesh):
        verts, faces = mesh
        verts = np.array(verts)
        areas = np.zeros((len(faces)))

        for i in range(len(areas)):
            areas[i] = (self.triangle_area(verts[faces[i][0]],
                                           verts[faces[i][1]],
                                           verts[faces[i][2]]))
            
        sampled_faces = (random.choices(faces, 
                                      weights=areas,
                                      cum_weights=None,
                                      k=self.output_size))
        
        sampled_points = np.zeros((self.output_size, 3))

        for i in range(len(sampled_faces)):
            sampled_points[i] = (self.sample_point(verts[sampled_faces[i][0]],
                                                   verts[sampled_faces[i][1]],
                                                   verts[sampled_faces[i][2]]))
        
        return sampled_points

class Normalize(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape)==2
        
        norm_pointcloud = pointcloud - np.mean(pointcloud, axis=0) 
        norm_pointcloud /= np.max(np.linalg.norm(norm_pointcloud, axis=1))

        return  norm_pointcloud
    
class ToTensor(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape)==2

        return torch.from_numpy(pointcloud)

def default_transforms():
    return transforms.Compose([PointSampler(1024), Normalize(), ToTensor()])

def get_top_k_dirs(root_dir, k):
    folders = [dir for dir in sorted(os.listdir(root_dir)) if os.path.isdir(os.path.join(root_dir, dir))]
    folder_freq = dict()
    for folder in folders:
        folder_freq[folder] = len(os.listdir(os.path.join(root_dir, folder, "train")))

    top_k = Counter(folder_freq).most_common(k)
    top_k_classes = [p[0] for p in top_k]
    return top_k_classes

class PointCloudData(Dataset):
    def __init__(self, root_dir, valid=False, folder="train", transform=default_transforms(), max_points=None, k=40, folders=None):
        self.root_dir = root_dir

        if not folders:
            self.folders = get_top_k_dirs(root_dir, k)
        else:
            self.folders = folders
        self.classes = {folder: i for i, folder in enumerate(self.folders)}
        
        self.transforms = transform if not valid else default_transforms()
        self.valid = valid
        self.files = []
        for i in range(len(self.folders)):
            category = self.folders[i]
            new_dir = root_dir/Path(category)/folder
            for file in tqdm(os.listdir(new_dir), desc=f"{category} ({i+1}/{len(self.folders)})"):
                if file.endswith('.off'):
                    if not max_points:
                        sample = {}
                        sample['pcd_path'] = new_dir/file
                        sample['category'] = category
                        self.files.append(sample)
                    else:
                        pcd_path = new_dir/file
                        with open(pcd_path, 'r') as f:
                            n_verts, _ = get_pointcloud_metadata(f)
                        if n_verts < max_points:
                            sample = {}
                            sample['pcd_path'] = pcd_path
                            sample['category'] = category
                            self.files.append(sample)

    def __len__(self):
        return len(self.files)

    def __preproc__(self, file):
        verts, faces = read_off(file)
        if self.transforms:
            pointcloud = self.transforms((verts, faces))
        return pointcloud

    def __getitem__(self, idx):
        pcd_path = self.files[idx]['pcd_path']
        category = self.files[idx]['category']
        with open(pcd_path, 'r') as f:
            pointcloud = self.__preproc__(f)
        return {'pointcloud': pointcloud, 
                'category': self.classes[category]}
    
class RandRotation_z(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape)==2

        theta = random.random() * 2. * math.pi
        rot_matrix = np.array([[ math.cos(theta), -math.sin(theta),    0],
                               [ math.sin(theta),  math.cos(theta),    0],
                               [0,                             0,      1]])
        
        rot_pointcloud = rot_matrix.dot(pointcloud.T).T
        return  rot_pointcloud
    
class RandomNoise(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape)==2

        noise = np.random.normal(0, 0.02, (pointcloud.shape))
    
        noisy_pointcloud = pointcloud + noise
        return  noisy_pointcloud
    
def load_modelnet40(dataset_dir, sampled_points=1024, max_points=None, num_classes=40):
    path = Path(dataset_dir)
    train_transforms = transforms.Compose([PointSampler(sampled_points), Normalize(), RandRotation_z(), RandomNoise(), ToTensor()])

    train_ds = PointCloudData(path, transform=train_transforms, max_points=max_points, k=num_classes)
    folders = train_ds.folders
    valid_ds = PointCloudData(path, valid=True, folder='test', transform=train_transforms, max_points=max_points, folders=folders)

    return train_ds, valid_ds

def get_dataloaders(data_dir, sampled_points=1024, val=False, num_classes=40, batch_size=16, **kwargs): 
    train_ds, test_ds = load_modelnet40(data_dir, max_points=None, sampled_points=sampled_points, num_classes=num_classes)

    if val:
        train_size = int(0.9 * len(train_ds))
        val_size = len(train_ds) - train_size
        train_ds, val_ds = random_split(train_ds, [train_size, val_size])

        train_dataloader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,**kwargs)
        val_dataloader = DataLoader(val_ds, batch_size=batch_size, shuffle=False,**kwargs)
        test_dataloader = DataLoader(test_ds, batch_size=batch_size, shuffle=False,**kwargs)

        return train_dataloader, val_dataloader, test_dataloader
    
    else:
        train_dataloader = DataLoader(train_ds, batch_size=batch_size, shuffle=True,**kwargs)
        test_dataloader = DataLoader(test_ds, batch_size=batch_size, shuffle=False,**kwargs)
        return train_dataloader, None, test_dataloader