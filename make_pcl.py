import pickle
import rospy
from util import get_rgba_pcd_msg
from sensor_msgs.msg import PointCloud2,Image
import json
import numpy as np
import pandas as pd
import argparse
from pclpy import pcl
import tf
from tf.transformations import quaternion_from_euler as qfe
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from geometry_msgs.msg import PoseStamped
from cv_bridge import CvBridge
import time
import glob
import cv2
import re


global sempcd
global args
global index
global poses
global br
global savepcd
global odom_trans

def get_colors():
    with open('mask2former/class.json','r') as f:
        j = json.load(f)
    return j['labels']

def class2color(cls,alpha = False):
    c = color_classes[cls]['color']
    if not alpha:
        return np.array(c).astype(np.uint8)
    else:
        return np.array([*c, 255]).astype(np.uint8)

def save_nppc(nparr,fname):
    s = nparr.shape
    if s[1] == 4:#rgb
        tmp = pcl.PointCloud.PointXYZRGBA(nparr[:,:3],np.array([color_classes[int(i)]['color'] for i in nparr[:,3]]))
    else:
        tmp = pcl.PointCloud.PointXYZ(nparr)
    pcl.io.save(fname,tmp)
    return tmp



def process():
	global sempcd
	global args
	global index
	global poses
	global br
	if args.filters:
		sempcd = sempcd[np.in1d(sempcd[:, 3], args.filters)]
	sem_msg = get_rgba_pcd_msg(sempcd)
	sem_msg.header.frame_id = 'world'
	semanticCloudPubHandle.publish(sem_msg)
	if args.trajectory:
		p = poses[index]
		rotation = pd.Series(p[3:7], index=['x', 'y', 'z', 'w'])
		br.sendTransform((p[0], p[1], p[2]), rotation, rospy.Time(time.time()), 'odom', 'world')
	index += 1
	if args.semantic and index < len(simgs):
		simg = cv2.imread(simgs[index],0)
		r,c = simg.shape
		semimg = colors[simg.flatten()].reshape((*simg.shape,3))
		semimgPubHandle.publish(bri.cv2_to_imgmsg(semimg, 'bgr8'))
	if args.origin and index < len(imgs):
		imgPubHandle.publish(bri.cv2_to_imgmsg(cv2.imread(imgs[index]), 'bgr8'))

color_classes = get_colors()
parser = argparse.ArgumentParser(description='Rebuild semantic point cloud')
parser.add_argument('-i','--input',default='result/hd_bak2/sempcd.pkl',type=argparse.FileType('rb'))
parser.add_argument('-m','--mode',default='indoor',choices=['indoor','outdoor'],help="Depend on the way to store the pickle file")
parser.add_argument('-f','--filters', default=None,nargs='+',type=int,help='Default to show all the classes, the meaning of each class refers to class.json')
parser.add_argument('-s','--save',default=None,help='Save to pcd file')
parser.add_argument('-t','--trajectory',default=None,help='Trajectory file, use to follow the camera')
parser.add_argument('--semantic',default=None,help='Semantic photos folder')
parser.add_argument('--origin',default=None,help='Origin photos folder')
args = parser.parse_args()



rospy.init_node('fix_distortion', anonymous=False, log_level=rospy.DEBUG)

odomPubHandle = rospy.Publisher('Odom',Odometry,queue_size = 5)
posePubHandle = rospy.Publisher('Pose',PoseStamped,queue_size = 5)

imgPubHandle = rospy.Publisher('Img',Image,queue_size = 5)
semanticCloudPubHandle = rospy.Publisher('SemanticCloud', PointCloud2, queue_size=5)
vecPubHandle = rospy.Publisher('VectorCloud', PointCloud2, queue_size=5)
testPubHandle = rospy.Publisher('TestCloud', PointCloud2, queue_size=5)
semimgPubHandle = rospy.Publisher('SemanticImg',Image,queue_size = 5)



savepcd = []
bri = CvBridge()
if args.semantic:
	simgs = glob.glob(args.semantic+'/*')
	simgs.sort(key = lambda x:int(re.findall('[0-9]{3,7}',x)[0]))
	colors = np.row_stack(pd.DataFrame(color_classes)['color']).astype('uint8')

if args.origin:
	imgs = glob.glob(args.origin+'/*')
	imgs.sort(key = lambda x:int(re.findall('[0-9]{3,7}',x)[0]))



index = 0
br = tf.TransformBroadcaster()
if args.trajectory:
	poses = np.loadtxt(args.trajectory, delimiter=',')


if args.mode == 'indoor':
	sempcds = pickle.load(args.input)
	for sempcd in sempcds:
		process()
	savepcd = np.concatenate(sempcds)
elif args.mode == 'outdoor':
	try:
		while True:
			sempcd = pickle.load(args.input)
			savepcd.append(sempcd)
			process()
	except EOFError:
		print('done')
		savepcd = np.concatenate(savepcd)
if args.save is not None:
	save_nppc(savepcd,args.save)