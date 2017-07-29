#!/usr/bin/awk -f
# in directory ARGV[1].functions create .S file per function + _000000_main.S and _data.S, `cat ARGV[1].functions/*.S` more or less recreates original file

function basename(path) {
  sub(".*/", "", path)
  return path
}

function funcPrint(line) {
  print line > DIR name ".S"
}

BEGIN {
  if (length(DIR) != match(DIR, "\\/[^/]*$")) {
    DIR = DIR "/"
  }
  DIR = DIR "" basename(ARGV[1]) ".functions/"
  system("mkdir -p " DIR " && rm -r " DIR "*.S 2> /dev/null")
  name = "main"
  kind = ".text"
  funcPrint(".text")
  funcPrint(".globl main")
}

/^\.data\s*$/ {
  kind = $1
  name = "_data"
}

/^\.text\s*$/ {
  kind = $1
  name = ""
}

".text" == kind && /^\w+:.*$/ {
  name = substr($1, 1, index($1, ":") - 1)
}

name != "" {
  funcPrint($0)
}

END {
  system("mv " DIR "main.S " DIR "_000000_main.S")
}