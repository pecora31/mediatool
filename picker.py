import sys
import tkinter as tk
from tkinter import filedialog

def main():
    initial_dir = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.focus_force()
    folder = filedialog.askdirectory(initialdir=initial_dir, title="Select Download Folder")
    root.destroy()
    if folder:
        # Print path with normal forward/backward slashes
        print(folder.replace('/', '\\'))

if __name__ == '__main__':
    main()
