#!/bin/bash
# v8 interaction surface grep (DELTA-5 mechanically derived)
GREP_TOKENS='onMouseDown|onContextMenu|onDrop|onPaste|onKeyDown|onTouchStart|onTouchEnd|aria-modal|role="dialog"|tabIndex|onChange|onInput|onSubmit|onFocus|onBlur'
grep -rnE "$GREP_TOKENS" apps/web/src/ \
  | grep -v node_modules \
  | sort > .omc/state/v8-interaction-grep-raw.txt
echo "raw grep hits: $(wc -l < .omc/state/v8-interaction-grep-raw.txt)"
