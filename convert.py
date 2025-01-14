import os
import re
import shutil
import json
import subprocess
import sys
import enum

i_format = ".mp3"
o_format = ".m4a"

ffmpeg_exe = "ffmpeg.exe"
exif_exe = "exiftool.exe"

ffmpeg_arg_1 = "-map 0:a -c:a aac"
working_dir = "out"

class DefaultMetaInfo:
    AlbumName    = None
    AuthorName   = None
    CoverPath    = None
    Year         = 1970

class FileMetainfo(DefaultMetaInfo):
    ExplicitCoverPath = None
    ExplicitPath      = None
    TrackName         = None
    TrackId           = -1

g_album_info = list()

class Tasks(enum.IntFlag):
    Convert = 1,
    Cover = 2,
    Tags = 4,
    CopyLyrics = 8,
    All = 7

def async_task_await(task, cmd):
    os.system(task + cmd)
    process = subprocess.Popen([task, cmd], None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.wait()

def prepare_meta(schema):
    file = open(schema, "rb")
    album_meta = json.load(file)
    for rec in album_meta:
        if (rec == "default"):
            #parse Default data
            default_data = FileMetainfo()
            for sub_rec in album_meta[rec]:
                key = list(sub_rec.keys())[0]
                if (key == "Author"):
                    default_data.AuthorName = sub_rec[key]
                if (key == "Album"):
                    default_data.AlbumName = sub_rec[key]
                if (key == "cover"):
                    default_data.CoverPath = sub_rec[key]
                if (key == "Year"):
                    default_data.Year = int(sub_rec[key])
            g_album_info.append(default_data)
        else:
            record = FileMetainfo()
            record.TrackId = int(rec)
            for sub_rec in album_meta[rec]:
                if (type(sub_rec) == str):
                    record.TrackName = sub_rec
                if (type(sub_rec) == dict):
                    #supported cover, file
                    key = list(sub_rec.keys())[0]
                    if (key == "cover"):
                        record.ExplicitCoverPath = sub_rec[key]
                    if (key == "file"):
                        record.ExplicitPath = sub_rec[key]
            g_album_info.append(record)
    return len(g_album_info) > 1

def add_tags():
    current_dir = os.getcwd() + '\\' + working_dir
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    for it in g_album_info:
        if (it.TrackId == -1):
            continue
        res = False
        pattern = re.compile(it.TrackName.replace('(',"\\(").replace(')',"\\)").replace('\'',"\'"), re.I)
        for i in files_list:
            match = pattern.search(i)
            if (match):
                src_path = "\"" + current_dir + '\\' + i + "\""
                tmp_path = "\"" + current_dir + '\\' + "tmp_" + i + "\""
                cmd = " -i " + src_path
                cmd += " -metadata " + " artist=" + "\"" + g_album_info[0].AuthorName + '\"'
                cmd += " -metadata " + " album=" + "\"" + g_album_info[0].AlbumName + '\"'
                cmd += " -metadata " + " date=" + "\"" + str(g_album_info[0].Year) + '\"'
                cmd += " -metadata " + " track=" + "\"" + str(it.TrackId) + '\"'
                cmd += " -metadata " + " title=" + "\"" + it.TrackName + '\"'
                cmd += " -c:0 copy " + tmp_path
                async_task_await(ffmpeg_exe, cmd)
                os.system("del " + src_path)
                os.system("move " + tmp_path + ' ' + src_path)
                res = True
                break
        #if (res == False):
        #    return False
    return True

def add_cover(album_cover):
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir + '\\' + working_dir) if os.path.isfile(os.path.join(current_dir + '\\' + working_dir,f))]
    for it in g_album_info:
        if (it.TrackId == -1):
            continue
        cover_path = None
        if (it.ExplicitCoverPath):
            cover_path = it.ExplicitCoverPath         
        else:
            cover_path = g_album_info[0].CoverPath
        if (os.access(working_dir + '\\' + cover_path, os.O_RDONLY) == False):
            shutil.copy(cover_path, working_dir + '\\' + cover_path)
        pattern = re.compile(it.TrackName.replace('(',"\\(").replace(')',"\\)"), re.I)
        res = False
        for i in files_list:
            match = pattern.search(i)
            if (match):
                src_path = '\"' + current_dir + '\\' + working_dir + '\\' + i + '\"'
                tmp_path = '\"' + current_dir + '\\' + working_dir + '\\' + "tmp_" + i + '\"'
                cmd = " -i " + src_path
                cmd += " -i " + '\"' + current_dir + '\\' + working_dir + '\\' + cover_path + '\"'
                cmd += " -map 0 -map 1 -c copy -disposition:1 attached_pic " + tmp_path
                async_task_await(ffmpeg_exe, cmd)
                os.system("del " + src_path)
                os.system("move " + tmp_path + ' ' + src_path)
                res = True
                break
        #if (res == False):
        #    return False
    return True

def mp3_convert():
    current_dir = os.getcwd()
    if (not os.path.exists(current_dir + "\\" + working_dir)):
        os.mkdir(current_dir + "\\" + working_dir)
    files_list = [f for f in os.listdir(current_dir) if os.path.isfile(os.path.join(current_dir,f))]
    for it in g_album_info:
        if (it.TrackId == -1):
            continue
        track_name = None
        if (it.ExplicitPath != None):
            track_name = it.ExplicitPath
        else:
            track_name = it.TrackName
        res = False
        pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)"), re.I)
        for i in files_list:
            match = pattern.search(i)
            if (match):
                cmd = " -i "
                cmd += "\"" + current_dir + "\\" + i + "\" "
                cmd += ffmpeg_arg_1 + " \"" + current_dir + "\\" + working_dir + "\\" + g_album_info[0].AuthorName + ' - ' + it.TrackName + o_format + "\""
                async_task_await(ffmpeg_exe, cmd)
                res = True
                break
        if (res == False):
            return False
    return True

def copy_lyrics():
    current_dir = os.getcwd()
    files_list = [f for f in os.listdir(current_dir + '\\' + working_dir) if os.path.isfile(os.path.join(current_dir + '\\' + working_dir,f))]
    for it in g_album_info:
        if (it.TrackId == -1):
            continue
        track_name = None
        if (it.ExplicitPath != None):
            track_name = it.ExplicitPath
        else:
            track_name = it.TrackName
        pattern = re.compile(track_name.replace('(',"\\(").replace(')',"\\)"), re.I)
        res = False
        for i in files_list:
            match = pattern.search(i)
            if (match):
                cmd = " -overwrite_original -TagsFromFile "
                cmd += '\"' + current_dir + '\\' + track_name  + i_format + '\"'
                cmd += " -Lyrics "
                cmd += '\"' + current_dir + '\\' + working_dir + '\\' + i + '\"'
                async_task_await(exif_exe, cmd)
                res = True
                break
        if (res == False):
            return False
    return True

def main(args):
    convert_task = Tasks.All
    if (len(args) > 1):
        skip_next = False
        for i in range(len(args)):
            if (skip_next):
                skip_next = False
                continue
            if (args[i] == "--lyrics"):
                convert_task = convert_task | Tasks.CopyLyrics
            if (args[i] == "--skip"):
                if (args[i+1].lower() == "convert" and (convert_task & Tasks.Convert)):
                    convert_task = convert_task ^ Tasks.Convert
                if (args[i+1].lower() == "cover" and (convert_task & Tasks.Cover)):
                    convert_task = convert_task ^ Tasks.Cover
                if (args[i+1].lower() == "tags" and (convert_task & Tasks.Tags)):
                    convert_task = convert_task ^ Tasks.Tags
    res = False
    res = prepare_meta("format.json")
    if (res == False):
        print("Convert file isn't a json file")
        return
    if (convert_task & Tasks.Convert):
        res = mp3_convert()
        if (res == False):
            print("Unable to find file from json scheme")
            return       
    if (convert_task & Tasks.Cover):
        res = add_cover("cover.jpg")
        if (res == False):
            print("Failed to add cover")
            return
    if (convert_task & Tasks.CopyLyrics):
        res = copy_lyrics()
        if (res == False):
            print("Unable copy lyrics from source file")
            return       
    if (convert_task & Tasks.Tags):
        res = add_tags()
        if (res == False):
            print("Failed to add track data")
            return
        
    print("Task complete!")

if __name__ == "__main__":
    main(sys.argv)