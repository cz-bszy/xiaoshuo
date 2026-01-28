"""
调试提取逻辑脚本
"""
import sys
from pathlib import Path

PROJECT_PATH = Path(r"e:\Test\xiaoshuo\projects\western-fantasy")
sys.path.insert(0, str(PROJECT_PATH))

from story_memory_adapter import StoryMemoryAdapter

def debug_chapter(chapter_num: int):
    print(f"🔧 Testing extraction on Chapter {chapter_num}...")
    
    adapter = StoryMemoryAdapter(db_name="debug_temp", clear_db=True)
    chapter_file = adapter._find_chapter_file(chapter_num)
    
    if not chapter_file:
        print("File not found")
        return
        
    content = chapter_file.read_text(encoding='utf-8')
    title = chapter_file.stem.split('_', 1)[1] if '_' in chapter_file.stem else ""
    
    try:
        entries = adapter.add_chapter_dry_run(chapter_num, content, title)
        print(f"\n✅ Result: Extracted {len(entries)} entries")
        if entries:
            print("First entry sample:")
            print(entries[0].lossless_restatement)
    except Exception as e:
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    debug_chapter(4)
