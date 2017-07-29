#!/bin/sh
# renames default-named string constants (grep -A 1 '_data:' $1 | grep -B 1 .string) to their value
# i.e. _abcdef_data: .string "Warning: low battery!"
# to   _abcdef_data_Warning__low_battery_: .string "Warning: low battery!"

ASM="$1"
file "${ASM}" | grep -q 'assembler source text' || {
  echo "Usage: $0 game.S (assembler source text produced by https://github.com/samunders-core/le_disasm)" 1>&2
  exit 1
}

THIS=`basename "$0"`
printRenamingScript() {
  echo "#!/bin/sh"
  echo "exec sed -i.before.${THIS}.bak -r '"
  awk '
    function asIdentifier(value) {
      result = substr(value, index(value, "\"") + 1)
      result = gensub(/[^a-zA-Z0-9_]/, "_", "g", result)
      return substr(result, 1, length(result) - 1)
    }
    /^_\w+_data/ {
      needle = ""
    }
    /^_\w+_data:/ {
      needle = substr($1, 1, length($1) - 1)
    }
    needle && /.string[[:space:]]+"(\\"|[^"])+"/ {
      print("s/" needle "/" needle "_" asIdentifier($0) "/")
      needle = ""
    }
  ' "${ASM}"
  echo "' "'"'"${ASM}"'"'
}

printRenamingScript | /bin/sh