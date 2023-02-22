"""Ingests an mp4 video and outputs """

import cv2
import mediapipe as mp
import numpy as np
import sys
import json
from typing import Dict

landmark_map = {
    0: "nose",
    1: "left_eye_inner",
    2: "left_eye",
    3: "left_eye_outer",
    4: "right_eye_inner",
    5: "right_eye",
    6: "right_eye_outer",
    7: "left_ear",
    8: "right_ear",
    9: "mouth_left",
    10: "mouth_right",
    11: "left_shoulder",
    12: "right_shoulder",
    13: "left_elbow",
    14: "right_elbow",
    15: "left_wrist",
    16: "right_wrist",
    17: "left_pinky",
    18: "right_pinky",
    19: "left_index",
    20: "right_index",
    21: "left_thumb",
    22: "right_thumb",
    23: "left_hip",
    24: "right_hip",
    25: "left_knee",
    26: "right_knee",
    27: "left_ankle",
    28: "right_ankle",
    29: "left_heel",
    30: "right_heel",
    31: "left_foot_index",
    32: "right_foot_index"
}

def landmark_list_to_dicts(landmark_list) -> Dict:
    return [{
        "x": this_landmark.x,
        "y": this_landmark.y,
        "z": this_landmark.z,
        "visibility": this_landmark.visibility,
        "index": i,
        "landmark_name": landmark_map[i]
    } for i, this_landmark in enumerate(landmark_list.landmark)]

    

#Load mediapipe drawing and pose utilities
mp_drawing = mp.solutions.drawing_utils
mp_pose = mp.solutions.pose

#create pose predictor
pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)

#set stream target
cap = cv2.VideoCapture(sys.argv[1])

if cap.isOpened() == False:
    print("Error opening video stream or file")
    raise TypeError

frame_width = int(cap.get(3))
frame_height = int(cap.get(4))

#Set input and output file locations
outdir, inputflnm = sys.argv[1][:sys.argv[1].rfind(
    '/')+1], sys.argv[1][sys.argv[1].rfind('/')+1:]
inflnm, inflext = inputflnm.split('.')
out_filename = f'{outdir}{inflnm}_annotated.{inflext}'
out_data_filename = f'{outdir}{inflnm}_annotated.json'
out = cv2.VideoWriter(out_filename, cv2.VideoWriter_fourcc(
    'M', 'J', 'P', 'G'), 10, (frame_width, frame_height))

frame_index = 0
out_data = []
#for each frame in the video...
with open(out_data_filename, "w") as data_outfile:
    while cap.isOpened():
        ret, image = cap.read()
        if not ret:
            break

        #feed frame into cv2 and get pose landmarks
        image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
        image.flags.writeable = False
        results = pose.process(image)
        print(results)
        print(results.pose_landmarks)
        print(type(results.pose_landmarks))

        #draw landmarks onto image
        image.flags.writeable = True
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        mp_drawing.draw_landmarks(
            image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)

        #write annotated image to annodated video file
        out.write(image)

        #write landmark locations to json file
        out_data.append({
            "frame_index": frame_index,
            "landmarks": landmark_list_to_dicts(results.pose_landmarks)
        })
        frame_index += 1

    pose.close()
    cap.release()
    out.release()

    data_outfile.write(json.dumps(out_data))

