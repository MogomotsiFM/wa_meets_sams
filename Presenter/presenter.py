import os
import time
import datetime
import logging

from itertools import takewhile

from collections import deque

from enum import Enum
from functools import reduce
from dataclasses import dataclass

from pywinauto.controls.uia_controls import ComboBoxWrapper, ButtonWrapper

from pywinauto.application import Application

from typing import Literal

from Common.directories import AppDirectories

class LoginStatus(Enum):
	SUCCESS= 1
	FAILURE= 2
	LOCKED_OUT= 4


# These values were discovered using: window.print_control_identifiers() function.
class ComboBoxControlId(Enum):
	YEAR   = 73
	GRADE  = 74
	ROOM   = 75 # Eg. 10A, 12C, ...
	CYCLE  = 72 # Term 1, 2, 3, or 4
	PHASE  = 60 # FET or Senior
	FORMAT = 40 # Report format

# Type definition
from typing import TypeAlias
Key: TypeAlias = Literal["years", "grades", "rooms", "cycles", "formats"]

logger = logging.getLogger()

class Presenter:
    # Cache the selected grade
    grade = None

    id_cb_map: dict[int, ComboBoxWrapper] = {}
    cache = {}
    # When we click "Print reports" this parameter should contain all our choices
    config: dict[Literal["years", "grades", "rooms", "cycles", "formats"], str] = {}
    # This is used to help with managing the combo_box_list cache and reseting the choices.
    # The idea is that if the grade is changed then the rooms, cycles, and formats must be changed
    # We keep this list to keep that order
    controls: list[Key] = ["years", "grades", "rooms", "cycles", "formats"]
    

    def __init__(self, app_dirs: AppDirectories):
        self.app_path = os.path.abspath(app_dirs.sams_path)
        self.report_path = os.path.abspath(app_dirs.reports_dir)
        self.cover_pg_path = os.path.abspath(app_dirs.cover_pgs_dir)

        self.app, self.window = self._start(self.app_path)

        self.cache = self.create_controls_cache()

    def home_directory(self):
        return self.app_path


    def select_combo_box_option(self, combo_box: ComboBoxWrapper, value: str):
        """
        There seems to be a bug with how pywinauto::ComboBox::select works.
        
        :param combo_box: The combo box object of interest
        :param value: The option in the combo box that we want to select
        """
        combo_box = combo_box.expand()
        kids = combo_box.children(control_type="List")
        for k in kids:
            logger.debug(k.texts())
        kids[0].item(value).invoke()


    def get_combo_box_options(self, options_combo: ComboBoxWrapper, key: str) -> list[str]:
        """
        Returns the list of options available from the combo box.
        These options are then forwarded to the GUI so that the user may select one of them.
        
        :param combo_box: The combo box object of interest
        """
        options_combo = options_combo.expand()
        kids = options_combo.children(control_type="List")
        labels = [k for ks in kids[0].texts() for k in ks]
        options_combo.collapse()

        return labels


    def _get_combo_boxes(self):
        cbs = self.window.descendants(control_type="ComboBox")
        id_combo_box_map = {cb.control_id(): cb for cb in cbs}
        return id_combo_box_map

    # If you set the grade then you have to set the room, cycle, and maybe format
    # If you then reset the grade then you have to set these values again
    def _reset_config_options(self, key:Literal["years", "grades", "rooms", "cycles", "formats"]):
        settings = takewhile(lambda k: k!=key, reversed(self.controls))
        logger.debug(f"\n\n{key}     To be reset: {list(settings)}")
        #settings = dropwhile(lambda k: k!=key, reversed(self.controls))
        #self.config = {k: self.config[k] for k in settings}
        for s in settings:
            self.config.pop(s, "")


    def _set_config_options(self, key:Literal["grades", "rooms", "cycles", "formats"], value):
        self.config[key] = value

        self._reset_config_options(key)

    
    def print_reports_config(self):
        """
        Returns the configuration required to start printing the reports to PDF.
        """
        return self.config


    def process_room(self, grade, room, report_file_path):
        """
        Prints the report of one learner to file

        : param window: The handle to the "Print learner progress reports" window
        : param learner_idx: Allows iterating over all the learners in a grade
        : param grade: The grade and name of the learner are used to name report files
        : param report_format_combo_box: 
        """
        self.window.window(best_match="Learners", control_type="Group").window(best_match="All", control_type="Button").click()

        self.window.window(best_match="Language to print", control_type="Group").English.click()

        self.window.window(best_match="Select filter options", control_type="Group").window(best_match="Selected learner", control_type="RadioButton").click()

        filename = f"{grade}_{room}"
        filename = os.path.join(report_file_path, filename)
        button = self.window.window(best_match="Print progress report", control_type="Button")

        self.print_pdf(button, filename)


    def print_cover_page(self, combo_box: ComboBoxWrapper, phase: Literal["FET", "Senior"], report_path: str):
        logging.getLogger().info(f"Printing the {phase} cover page to PDF")
        self.select_combo_box_option(combo_box, phase)

        filename = f"{phase}_report_cover"
        filename = os.path.join(report_path, filename)

        button = self.window.window(best_match="Print blank report cover", control_type="Button")
        
        self.print_pdf(button, filename)


    def print_pdf(self, button: ButtonWrapper, filename: str):
        button.click()

        # Ensure we always print to PDF by selecting the correct printer in the print setup dialog
        print_setup_window = self.window.window(best_match="Print setup", control_type="Window")
        print_destination_combo_box = print_setup_window.window(best_match="Name", control_type="ComboBox")
        self.select_combo_box_option(print_destination_combo_box, "Microsoft Print to PDF")

        print_setup_window.OK.click()

        parent = self.window.window(best_match="Print reports", control_type="Window")
        parent.window(parent=parent, best_match="Print report", control_type="Button").click()

        self.window.Print.OK.click()

        # A new window in a new tree is opened
        save_window = self.app.window(best_match="Printing records", control_type="Window")

        save_window = save_window.window(best_match="Save print output as", control_type="Window")
        save_window.wait(wait_for="ready", timeout=30)

        # select_combo_box_option(save_window, "File name:", filename)
        edit = save_window.window(best_match="File name", control_type="ComboBox").window(control_type="Edit")
        edit.set_edit_text(filename)
        save_window.Save.click()

        parent.wait(wait_for="ready", timeout=30)
        parent.Done.click()


    def report_printing_done(self):
        parent = self.window.window(best_match="Print progress reports", control_type="Window")
        parent.Done.click()


    def exit_mainwindow(self):
        self.window.Exit.click()

    
    def home(self):
        # Navigate from the Print reports window to the home window
        self.window.window(best_match="Curriculum module menu", control_type="Button").click()

        self.window.window(best_match="Main menu", control_type="Button").click()


    def copy_db_before_opening(self, desired_copy_db_flag):
        actual_copy_db_flag = self.get_copy_db_checkbox_state()
        if desired_copy_db_flag != actual_copy_db_flag:
            checkbox = self.controls_cache('self.window["Copy database before opening"]')
            checkbox.toggle()


    def get_copy_db_checkbox_state(self):
        checkbox = self.controls_cache('self.window["Copy database before opening"]')
        state = checkbox.get_toggle_state()

        return state>0


    def local_dbs_list(self):
        lst = self.controls_cache('self.window["Databases on this computer"].window(control_type="List")')
        databases = lst.texts()
        dbs = [item for sublist in databases for item in sublist]
        return dbs


    def last_used_networked_db(self):
        textbox = self.controls_cache('self.window["Database on a networked computer"].window(control_type="Edit")')
        return textbox.get_value()
    

    def select_local_db(self, db_name):
        lst = self.controls_cache('self.window["Databases on this computer"].window(control_type="List")')
        lst.item(db_name).click_input()


    def set_networked_db(self, db_path):
        textbox = self.controls_cache('self.window["Database on a networked computer"].window(control_type="Edit")')

        textbox.set_edit_text(db_path)


    def use_networked_db(self) -> None:
        radio = self.controls_cache('self.window["On the network"]')
        radio.click()


    def use_networked_db_radio_state(self) -> bool:
        radio = self.controls_cache('self.window["On the network"]')
        return radio.is_selected()
    

    def use_local_db(self) -> None:
        radio = self.controls_cache('self.window["On this computer"]')
        radio.click()


    def use_local_db_radio_state(self) -> bool:
        radio = self.controls_cache('self.window["On this computer"]')
        return radio.is_selected()
                             

    def continue_to_login(self):
        if self.use_local_db_radio_state():
            self.window["Databases on this computer"].window(best_match="continue").click_input()
        else:
            self.window["Databases on a networked computer"].window(best_match="continue").click_input()

        # POPIA Acknowledgement
        self.window.window(title_re="POPIA").window(best_match="I accept").click()

        login_window = self.window.window(title_re="User Login", control_type="Window")
        login_window.wait(wait_for="ready", timeout=15)


    def create_controls_cache(self):
        """
        Cache the controls in the first widget of SA-SAMS.
        This should make the Presenter more responsive and the view snappy.

        The naming convention of the keys was strictly meant to make the transition easy
        to verify in the absence of automated tests.
        
        It is for no other purpose.
        """
        cache = {}

        self.use_local_db()

        # pywinauto is lazy so we call WindowSpecification::wait() to force evaluation...
        cache['self.window["Copy database before opening"]'] = self.window["Copy database before opening"].wait("ready")

        cache['self.window["Databases on this computer"].window(control_type="List")'] = self.window["Databases on this computer"].window(control_type="List").wait("ready")

        cache['self.window["On this computer"]'] = self.window["On this computer"].wait("ready")

        self.use_networked_db()

        cache['self.window["Database on a networked computer"].window(control_type="Edit")'] = self.window["Database on a networked computer"].window(control_type="Edit").wait("ready")

        cache['self.window["On the network"]'] = self.window["On the network"].wait("ready")

        return cache


    def controls_cache(self, key: str):#, timeout=2):
        try:
            return self.cache[key]
        except:
            self.cache[key] = eval(f"{key}.wait('ready', timeout=20)")
            return self.cache[key]


    def go_to_progress_report_widget(self):
        # Navigate to the school reports configuration tab
        home = self.controls_cache('self.window.window(best_match="Curriculum Related Data")')
        #self.window.window(best_match="Curriculum Related Data").click()
        home.click()
        self.window.window(best_match="Print Learner Progress Reports").click()
        # The following is deliberate
        self.window.window(best_match="Print Learner Progress Reports").click()

        self.id_cb_map = self._get_combo_boxes()


    def login(self, username, password) -> tuple[LoginStatus, str]:
        login_window = self.window.window(title_re="User Login", control_type="Window")
        # Hard-code the username to force the creation of a profile specifically for this application.
        # This will allow us to lock down the permissions of the application.
        # The same bug is triggered here!!!!
        login_window.window(title_re="User Details").Edit1.set_text(username)
        login_window.window(title_re="User Details").Edit2.set_text(password)

        login_window.window(best_match="Log In", control_type="Button").click()

        try:
            self.window.EdusolSAMS.wait("ready", timeout=1)
            dlg_msgs = self.window.EdusolSAMS.window(control_type="Text").texts()
            dlg_msg = reduce(lambda a, b : a + b, dlg_msgs)
            self.window.EdusolSAMS.OK.click()
            
            if "success" in dlg_msg:
                return LoginStatus.SUCCESS, dlg_msg
            else:
                return LoginStatus.FAILURE, dlg_msg
        except Exception as exp:
            login_failure = self.window.window(parent=login_window, best_match="User message")
            # message: You have not entered the correct message
            # message: 
            login_failure_msgs = login_failure.window(control_type="Text").texts()
            login_failure_msg  = reduce(lambda a, b : a + b, login_failure_msgs)
            login_failure.OK.click()
            
            # It is possible that we have tried to login too many times
            # and have been locked out.
            try:
                login_window.EdusolSAMS.wait("ready", timeout=1)
                login_lockout_msgs = login_window.EdusolSAMS.window(control_type="Text").texts()
                login_lockout_msg  = reduce(lambda a, b : a + b, login_lockout_msgs)
                login_window.EdusolSAMS.OK.click()
            except Exception as exp:
                # If an exception is thrown it means there was no dialog that indicates that we tried too
                # many time. So, we failed, but can still try again.
                return LoginStatus.FAILURE, login_failure_msg
            else:
                return LoginStatus.LOCKED_OUT, login_lockout_msg


    def cancel_login(self):
        # PRE-CONDITON: The correct window is open
        login_window = self.window.window(title_re="User Login", control_type="Window")
        login_window.window(best_match="Exit", control_type="Button").click()
        

    def _start(self, path):
        app_location = os.path.join(path, "EdusolSAMS.exe")

        while(True):
            try:
                app = Application(backend="uia").start(app_location)

                window = app.window(title_re="SA-SAMS")
                window.wait("ready", timeout=30)
                window.set_focus()
            except Exception as exp:
                # Most likely the login window did not come up. There is a note somewhere about this.
                # Check that SA-SAMS is not running
                if app.is_process_running():
                    app.kill()

                    logger.debug("Process was running")
                logger.debug("Trying to start the program again...")
                time.sleep(5)
            else: # Executed if no exception is raised.
                break

        self.app = app
        self.window = window

        return app, window


    def get_years_list(self):
        year_combo_box = self.id_cb_map[ComboBoxControlId.YEAR.value]
        year_combo_box.draw_outline()
        years = self.get_combo_box_options(year_combo_box, "years")
        return years
    

    def select_year(self, year):
        year_combo_box = self.id_cb_map[ComboBoxControlId.YEAR.value]

        self.select_combo_box_option(year_combo_box, value=year)

        self._set_config_options("years", year)

        # Do we have a popup error message
        try:
            parent = self.window.window(best_match="Print progress reports", control_type="Window")
            parent = parent.window(best_match="User Message", control_type="Window")
            parent.wait(wait_for="ready")
            msgs = parent.window(control_type="Text").texts()
            parent.OK.click()

            # We failed because we found a popup dialog with an error message
            return False, msgs[0]
        except Exception as exp:
            logger.debug("Dialog not found")
            return True, ""

    
    def get_grades_list(self):
        grade_combo_box = self.id_cb_map[ComboBoxControlId.GRADE.value]
        grade_combo_box.draw_outline()
        grades = self.get_combo_box_options(grade_combo_box, "grades")

        return grades
    

    def select_grade(self, desired_grade):
        grade_combo_box = self.id_cb_map[ComboBoxControlId.GRADE.value]
        self.select_combo_box_option(grade_combo_box, value=desired_grade)

        self._set_config_options("grades", desired_grade)


    def get_selected_grade(self):
        return self.config["grades"]
    

    def get_rooms_list(self):
        grade = self.get_selected_grade()

        if "All" in grade:
            return ["All"]
        else:
            room_combo_box = self.id_cb_map[ComboBoxControlId.ROOM.value]
            room_combo_box.draw_outline()
            rooms = self.get_combo_box_options(room_combo_box, "rooms")

            return rooms
    

    def select_room(self, desired_room):
        grade = self.get_selected_grade()
        logger.debug(f"Selected grade: {grade}")
        if "All" not in grade:
            room_combo_box = self.id_cb_map[ComboBoxControlId.ROOM.value]
        
            self.select_combo_box_option(room_combo_box, value=desired_room)

        self._set_config_options("rooms", desired_room)


    def get_report_cycles(self):
        cycle_combo_box = self.id_cb_map[ComboBoxControlId.CYCLE.value]
        cycle_combo_box.draw_outline()
        return self.get_combo_box_options(cycle_combo_box, "reports")


    def select_report_cycle(self, desired_cycle):
        cycle_combo_box = self.id_cb_map[ComboBoxControlId.CYCLE.value]
        self.select_combo_box_option(cycle_combo_box, value=desired_cycle)

        self._set_config_options("cycles", desired_cycle)

        # We cannot select the format unless we first click the GO button
        # to retrieve the list of learners
        # In our case it is possible there are no students in a class/grade.
        # But, in a real school this may not happen unless ...
        self.window.window(best_match="Select options", control_type="Group").window(best_match="GO", control_type="Button").click()
        try:
            parent = self.window.window(best_match="Print progress reports", control_type="Window")
            parent = parent.window(best_match="User Message", control_type="Window")
            parent.wait(wait_for="ready", timeout=1)
            msgs = parent.window(control_type="Text").texts()
            parent.OK.click()

            logging.getLogger().warning(msgs[0])

            # We failed because we found a popup dialog with an error message
            return False, msgs[0]
        except Exception as exp:
            return True, ""


    def get_report_formats(self):
        format_combo_box = self.id_cb_map[ComboBoxControlId.FORMAT.value]
        return self.get_combo_box_options(format_combo_box, "formats")
        

    def select_report_format(self, desired_format):
        format_combo_box = self.id_cb_map[ComboBoxControlId.FORMAT.value]
        self.select_combo_box_option(format_combo_box, value=desired_format)

        self._set_config_options("formats", desired_format)


    def is_running(self):
        return self.app.is_process_running()


    def run(self, grade: str, room: str, cycle:str, format: str):
        desired_grade = grade
        desired_room  = room
        desired_cycle = cycle
        if "All" in desired_grade:
            gs = self.get_grades_list()
            grades = [g for g in gs if "All" not in g]
        else:
            grades = [desired_grade]
        
        for grade in grades:
            self.select_grade(grade)
            
            if "All" in desired_grade or "All" in desired_room:
                rms = self.get_rooms_list()
                rooms = [rm for rm in rms if "All" not in rm]
            else:
                rooms = [desired_room]

            for room in rooms:
                logging.getLogger().info(f"Writing report dossier for Grade {room} to file.")

                self.select_room(room)

                cycles = self.get_report_cycles()
                cycle_ = [c for c in cycles if desired_cycle in c]
                is_successful, msg = self.select_report_cycle(cycle_[0])

                if is_successful:
                    self.select_report_format(format)

                    self.process_room(grade, room, self.report_path)
                else:
                    logger.warning(f"Swallowed error: {msg}")

        cb = self.id_cb_map[ComboBoxControlId.PHASE.value]
        self.print_cover_page(cb, "FET", self.cover_pg_path)
        self.print_cover_page(cb, "Senior", self.cover_pg_path)

