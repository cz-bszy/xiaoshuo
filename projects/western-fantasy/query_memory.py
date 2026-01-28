from story_state_manager import StoryStateManager
import sys

# Set recursion limit just in case
sys.setrecursionlimit(2000)

try:
    print("Initializing Manager...")
    manager = StoryStateManager()
    print("Generating Context...")
    # Use fewer topics to avoid complex recursion?
    context = manager.generate_context_for_writing(61, topics=["第一艘船", "领地贸易", "马库斯"])
    print("Context Generated!")
    print("="*50)
    print(context)
    print("="*50)
except Exception as e:
    print(f"Error: {e}")
