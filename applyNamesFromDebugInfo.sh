#!/bin/sh

[ -f "$1" ] && [ -f "$2" ] || {
  echo "Usage: $0 game.le.exe game.S (argument order doesn't matter)" 1>&2
  exit 1
}

URL='https://github.com/open-watcom/travis-ci-ow-builds/raw/master/binl/wdump'
WD=/tmp/wdump
[ ! -x "${WD}" ] && wget -O "${WD}" "${URL}" && chmod +x "${WD}"
[ -x "${WD}" ] || {
  echo "Failed to obtain ${WD} from ${URL}" 1>&2
  exit 2
}

EXE="$1"
ASM="$2"
file "$1" | grep -q 'assembler source text' && {
  EXE="$2"
  ASM="$1"
}
file "${ASM}" | grep -q 'assembler source text' || {
  echo "Neither of given files is assembler source text" 1>&2
  exit 3
}

debugInfo() {
  "${WD}" -Dx "${EXE}"
}

debugInfo | grep 'No debugging information found' && exit 4

relocBaseAddress() { # exe number
  "${WD}" -r "$1" | grep -A 1 "object $2:" | sed -n 'x;n;s/^\s\+relocation base address\s\+=\s\+0*\([0-9A-F]\+\)H\r\?/0x\1/;p'
}

CS=1
DS=3
CODE_RELOC_ADDRESS=`relocBaseAddress "${EXE}" "${CS}"`
DATA_RELOC_ADDRESS=`relocBaseAddress "${EXE}" "${DS}"`

printRenamingScript() {
  echo "#!/bin/sh"
  echo "exec sed -i -r '"
  debugInfo | tr ':\r' '  ' | awk '
    /Name/{name=$2}
    /address\s+=\s+000'${CS}'\s+/{address=sprintf("$(('$CODE_RELOC_ADDRESS' + 0x%s))", $4);type="func"}
    /address\s+=\s+000'${DS}'\s+/{address=sprintf("$(('$DATA_RELOC_ADDRESS' + 0x%s))", $4);type="data"}
    /kind/{print "printf \"s/_%06x_%s/_%06x_%s_"name"/\\n\"",address,type,address,type}
  ' | /bin/sh | sed -re 's/(IF|__)@/\1_at_/g'
  echo "' "'"'"${ASM}"'"'
}

printRenamingScript | /bin/sh
