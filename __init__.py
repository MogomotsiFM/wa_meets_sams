# In package_name/__init__.py
import os

# Get the absolute path of the current directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Add a 'utils' subdirectory to the package's search path
common_dir = os.path.join(current_dir, "Common")
__path__.append(common_dir)

pre_dir = os.path.join(current_dir, "Presenter")
__path__.append(pre_dir)

pro_dir = os.path.join(current_dir, "Processes")
__path__.append(pro_dir)

server_dir = os.path.join(current_dir, "Server")
__path__.append(server_dir)

v_dir = os.path.join(current_dir, "View")
__path__.append(v_dir)

m_dir = os.path.join(current_dir, "Messangers")
__path__.append(m_dir)
