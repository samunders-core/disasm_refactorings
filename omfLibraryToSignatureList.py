#!/usr/bin/python3
# vim:sw=4

from getopt import gnu_getopt, GetoptError
import re
import sys
import subprocess
import tempfile
import shutil
from io import StringIO
from os import listdir, path

STATE_SEARCH_FUNCTION = 0
STATE_PROCESS_ASSEMBLY = 1
STATE_SEARCH_ROUTINE_SIZE = 2
OPT_LIMIT_SIGNATURE_PATTERN_SIZE = 20


class LibOpcode:
    def __init__(self):
        self.opcode_size = 0
        self.opcode = ""
        self.opcode_params = []
        self.text = ""
        self.type = ""
        self.is_valid = False


class LibObject:
    def __init__(self):
        self.object_name = ""
        self.object_type = ""
        self.object_data = []
        self.object_size = ""
        self.match_string = []

    def get_size(self):
        size = 0
        for op in self.object_data:
            size = size + op.opcode_size
        return size


class LibSegment:
    def __init__(self):
        self.segment_name = ""
        self.segment_class = ""
        self.bitness = ""
        self.object_list = []


class Librarian:
    def __init__(self):
        self._lib_path = ""
        self.input_filename = ""
        self.output_filename = ""
        self.temp_directory = ""
        self.segment_list = []

    @staticmethod
    def print_help():
        print(
            """Usage: %s OPTIONS OMF_LIBRARY
    
    The script requires Watcom Wdis tool to disassemble OMF libraries

    LIBRARY:            path to OMF library file (*.lib)
    OPTIONS:
      -h  --help		shows this help text
      -o FILE		    outputs signatures to FILE instead of stdout"""
            % (sys.argv[0]))

    @staticmethod
    def call_process(args):
        try:
            retcode = subprocess.call(args, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            if retcode < 0:
                print("Error: %s returned with " % (args[0]), retcode, file=sys.stderr)
                sys.exit(1)
            else:
                None
        except OSError as e:
            print("Process call failed:", e, file=sys.stderr)
            sys.exit(1)

    def extract_library(self):
        self.temp_directory = tempfile.mkdtemp()
        self.call_process(["wlib", "-x", "-d=" + self.temp_directory, self.input_filename])

    def check_element(self, f, f_ext):
        if path.isfile(path.join(self.temp_directory, f)):
            _, file_extension = path.splitext(f)
            if file_extension == f_ext:
                return True
        return False

    def extract_object_files(self):
        file_list = [f for f in listdir(self.temp_directory) if self.check_element(f, ".o")]
        for file in file_list:
            self.call_process(["wdis", path.join(self.temp_directory, file), "-l"])

    def process_list_files(self):
        file_list = [f for f in listdir(self.temp_directory) if self.check_element(f, ".lst")]
        for file in file_list:
            if file == "intxa386.lst":
                self.fix_wdis_87emu(path.join(self.temp_directory, file))
            self.split_segments(path.join(self.temp_directory, file))

    @staticmethod
    def process_segment_header(header, seg):
        m = re.match(r"Segment: (\S+) \S+ (\S+) ", header)
        if m and len(m.groups()) == 2:
            seg.segment_class = m.group(1)
            seg.bitness = m.group(2)

    @staticmethod
    def search_label(line):
        m = re.match(r"^[0-9a-fA-F]+\s+(\S+):$", line)
        if m is not None and len(m.groups()) == 1:
            if m.group(1).find("L$") == -1:
                return "g", m.group(1)
            else:
                return "l", m.group(1)
        return "", None

    def search_assembly(self, data, obj):
        m = re.match(r"^[0-9a-fA-F]+\s+((?:\s[0-9a-fA-F]{2})+)(?:\s+(\S+)\s*(.*)$|$)", data)
        op = LibOpcode()
        if m is not None and len(m.groups()) == 3:
            op.opcode = m.group(2)
            op.opcode_size = int(len("".join(m.group(1).split())) / 2)
            if m.group(3):
                op.opcode_params = m.group(3).split(",")
            op.is_valid = True
            if op.opcode:
                op.type = "CODE"
            else:
                op.type = "CODE_SIZE"
        else:
            label_type, label_name = self.search_label(data)
            if label_name is not None:
                op.opcode = label_name
                op.opcode_size = 0
                op.is_valid = True
                if label_type == "g":
                    op.type = "G_LABEL"
                elif label_type == "l":
                    op.type = "L_LABEL"
            else:
                m = re.match(r"^(\S+)\s+(.+)$", data)
                if m and len(m.groups()) == 2:
                    op.opcode = m.group(1)
                    op.opcode_size = 0
                    if m.group(2):
                        op.opcode_params = m.group(2).split(",")
                    op.is_valid = True
                else:
                    op.text = data
        obj.object_data.append(op)

    @staticmethod
    def create_match_string(obj):
        s = StringIO()
        label = ""
        limit_opcode_count = OPT_LIMIT_SIGNATURE_PATTERN_SIZE
        opcode_count = 0
        first_function = True
        limit_break = False
        for op in obj.object_data:
            if op.is_valid:
                if op.type == "CODE":
                    if opcode_count >= limit_opcode_count:
                        limit_break = True
                        continue
                    opcode_count += 1
                    s.write(r"\s*" + op.opcode)
                    if op.opcode_params:
                        s.write(r"[^,\n]+")
                        count = len(op.opcode_params)
                        for i in range(1, count):
                            s.write(r",[^,\n]+")
                elif op.type == "G_LABEL":
                    if not first_function:
                        s.write(r"[\n\n]+")
                        obj.match_string.append((label, s.getvalue()))
                        s.close()
                        opcode_count = 0
                        s = StringIO()
                    s.write(r"_[0-9a-fA-F]+_func:\s+")
                    label = op.opcode
                    first_function = False
                elif op.type == "L_LABEL":
                    if opcode_count >= limit_opcode_count:
                        limit_break = True
                        continue
                    s.write(r"\s+\S+\s+")
            else:
                if opcode_count >= limit_opcode_count:
                    limit_break = True
                    continue
                s.write(r"[^\n]\s*")
                opcode_count += 1
        if limit_break is False:
            s.write(r"[\n\n]+")
        obj.match_string.append((label, s.getvalue()))
        s.close()

    @staticmethod
    def search_routine_summary(data):
        m = re.match(r"Routine Size: ([0-9]+) byte", data)
        if m is not None and len(m.groups()) == 1:
            return int(m.group(1))
        else:
            return None

    def process_segment_data(self, data, seg):
        if seg.segment_class != r"_TEXT":
            return

        obj = LibObject()
        state = STATE_SEARCH_FUNCTION
        for line in data:
            line = line.strip()
            if state == STATE_SEARCH_FUNCTION:
                if not line:
                    continue
                label = self.search_label(line)
                if label is not None:
                    obj.object_name = label
                    state = STATE_PROCESS_ASSEMBLY
                    # fall through to next state to capture function label into an opcode
            if state == STATE_PROCESS_ASSEMBLY:
                if not line:
                    self.create_match_string(obj)
                    obj.object_size = obj.get_size()
                    state = STATE_SEARCH_ROUTINE_SIZE
                    continue
                self.search_assembly(line, obj)
            if state == STATE_SEARCH_ROUTINE_SIZE:
                if not line:
                    continue
                else:
                    size = self.search_routine_summary(line)
                    if size is not None:
                        if size == obj.object_size:
                            seg.object_list.append(obj)
                        else:
                            print("Incorrect function size in %s::%s (%i/%i)" % (
                                seg.segment_name, obj.object_name, obj.object_size, size), file=sys.stderr)
                        obj = LibObject()
                        state = STATE_SEARCH_FUNCTION
                    else:
                        continue

    @staticmethod
    def fix_wdis_87emu(list_file):
        with open(list_file, "r", encoding="iso-8859-1") as f:
            text = f.read()
            part1, part2, part3 = re.split(r"([0-9a-fA-F]+\s+CD 34 C3.*)", text)
            part4, part5, part6 = re.split(r"([0-9a-fA-F]+\s+CD 3E.*)", part3)
            f.close()
            f = None
            text_buffer = StringIO()
            text_buffer.write(part1)
            new_text = "0177  CD 34				int		0x34\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 35				int		0x35\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 36				int		0x36\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 37				int		0x37\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 38				int		0x38\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 39				int		0x39\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 3A				int		0x3a\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 3B				int		0x3b\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 3C				int		0x3c\n" \
                       "0179  C3				ret\n" \
                       "0177  CD 3D				int		0x3d\n" \
                       "0179  C3				ret\n"
            text_buffer.write(new_text)
            text_buffer.write(part5)
            text_buffer.write(part6)
            with open(list_file, 'w', encoding="iso-8859-1") as fd:
                text_buffer.seek(0)
                shutil.copyfileobj(text_buffer, fd)

    def split_segments(self, file):
        with open(file, "r", encoding="iso-8859-1") as f:
            text = f.read()
            segments = re.split(r"(Segment: \S+ \S+ \S+ \S+ \S+)", text)
            m = re.match(r"Module: (\S+)", segments[0])
            module_name = m.group(1)
            segment_count = len(segments[1:])
            if segment_count % 2 != 0:
                print('Error: Unexpected number', file=sys.stderr)
                sys.exit(1)
            for i in range(1, segment_count, 2):
                seg = LibSegment()
                seg.segment_name = module_name
                self.process_segment_header(segments[i], seg)
                self.process_segment_data(StringIO(segments[i + 1]), seg)
                self.segment_list.append(seg)
            f.close()

    def print_results(self):
        for seg in self.segment_list:
            if seg.object_list:
                print("%s\t%s\t%s" % (seg.segment_name, seg.segment_class, seg.bitness))
                for obj in seg.object_list:
                    for label, match_string in obj.match_string:
                        print("\t%s\t%s" % (label, match_string))

    def main(self):
        try:
            opts, args = gnu_getopt(sys.argv[1:], "h:o:",
                                    ("help", "output-file"))

        except GetoptError as message:
            print('Error: ', message, file=sys.stderr)
            sys.exit(1)

        for opt, arg in opts:
            if opt in ('-h', '--help'):
                self.print_help()
                sys.exit(0)
            elif opt in ('-o',):
                self.output_filename = arg

        if len(args) == 1:
            self.input_filename = args[0]
        elif len(args) > 1:
            print('Error: Too many arguments', file=sys.stderr)
            sys.exit(1)
        else:
            self.print_help()
            sys.exit(1)

        self.extract_library()
        self.extract_object_files()
        self.process_list_files()
        self.print_results()


lib = Librarian()
lib.main()
