import os
import gc
import time
import analogio
import board
import digitalio
import pwmio
import usb_hid
machine = None
microcontroller = None
try:
    import machine
except:
    try:
        import microcontroller
    except:
        print("no machine & microcontroller module support")
thread = None
try:
    import _thread as thread
except:
    print("no multi-threading module support")

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as K
from adafruit_hid.mouse import Mouse
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode as C

from scheduler import Scheluder, Condition, Task, Message
from common import ticks_ms, ticks_add, ticks_diff, sleep_ms

cpu_freq = 100000000
if machine:
    machine.freq(cpu_freq)
    print("freq: %s mhz" % (machine.freq() / 1000000))
if microcontroller:
    microcontroller.cpu.frequency = cpu_freq
    print("freq: %s mhz" % (microcontroller.cpu.frequency / 1000000))


FN = "FN"
MOUSE_LEFT = 200
MOUSE_RIGHT = 201
MOUSE_UP = 202
MOUSE_DOWN = 203
MOUSE_MIDDLE = 204


def setup_pin(pin, direction, pull = None):
    io = digitalio.DigitalInOut(pin)
    io.direction = direction
    if pull is not None:
        io.pull = pull
    return io


def get_level_value(pin, max_level = 4096, zero_zone = 200, negative = 1):
    level_value = (pin.value * max_level) // 65536
    middle_value = max_level // 2
    value = middle_value - level_value
    if abs(value) < zero_zone:
        return 0
    elif abs(value) < (middle_value - (2 * zero_zone)):
        return value * negative
    else:
        return (value * middle_value * negative) // abs(value)


class Button(object):
    def __init__(self, pin, direction, pull):
        self.io = digitalio.DigitalInOut(pin)
        self.io.direction = direction
        self.io.pull = pull
        self.status = "up"

    def click(self):
        if self.status == "up":
            if self.down():
                self.status = "debounce"
        elif self.status == "debounce":
            if self.up():
                self.status = "up"
                return True
        return False

    def press(self):
        return self.status == "debounce"

    def continue_click(self):
        if self.status == "up":
            if self.down():
                self.status = "debounce"
                return True
        elif self.status == "debounce":
            if self.down():
                return True
            elif self.up():
                self.status = "up"
                return False
        return False

    def down(self):
        return not self.io.value

    def up(self):
        return self.io.value


class CustomKeyBoard(object):
    def __init__(self, mouse):
        self.mouse = mouse
        self.keyboard = Keyboard(usb_hid.devices)
        self.keyboard_layout = KeyboardLayoutUS(self.keyboard)
        self.consumer_control = ConsumerControl(usb_hid.devices)
        self.x_lines = [
            setup_pin(board.GP0, digitalio.Direction.OUTPUT), # 0
            setup_pin(board.GP1, digitalio.Direction.OUTPUT), # 1
            setup_pin(board.GP2, digitalio.Direction.OUTPUT), # 2
            setup_pin(board.GP3, digitalio.Direction.OUTPUT), # 3
            setup_pin(board.GP4, digitalio.Direction.OUTPUT), # 0
            setup_pin(board.GP5, digitalio.Direction.OUTPUT), # 1
            setup_pin(board.GP6, digitalio.Direction.OUTPUT), # 2
            setup_pin(board.GP7, digitalio.Direction.OUTPUT), # 3
            setup_pin(board.GP8, digitalio.Direction.OUTPUT), # 4
            setup_pin(board.GP21, digitalio.Direction.OUTPUT), # 5
            setup_pin(board.GP10, digitalio.Direction.OUTPUT), # 6
            setup_pin(board.GP11, digitalio.Direction.OUTPUT), # 7
            setup_pin(board.GP12, digitalio.Direction.OUTPUT), # 8
            setup_pin(board.GP13, digitalio.Direction.OUTPUT), # 9
        ]
        self.y_lines = [
            setup_pin(board.GP14, digitalio.Direction.INPUT, digitalio.Pull.UP), # 0
            setup_pin(board.GP15, digitalio.Direction.INPUT, digitalio.Pull.UP), # 1
            setup_pin(board.GP16, digitalio.Direction.INPUT, digitalio.Pull.UP), # 2
            setup_pin(board.GP17, digitalio.Direction.INPUT, digitalio.Pull.UP), # 3
            setup_pin(board.GP18, digitalio.Direction.INPUT, digitalio.Pull.UP), # 4
            setup_pin(board.GP19, digitalio.Direction.INPUT, digitalio.Pull.UP), # 5
        ]
        self.keys = [
            [MOUSE_LEFT, MOUSE_UP, MOUSE_DOWN, MOUSE_RIGHT, MOUSE_MIDDLE, (K.F4, K.F10), (K.F5, K.F11), (K.F6, K.F12), (K.F1, K.F7), (K.F2, K.F8), (K.F3, K.F9), None, None, None],
            [K.ESCAPE, K.Q, K.W, K.E, K.R, K.T, K.Y, K.U, K.I, K.O, K.P, K.LEFT_BRACKET, K.RIGHT_BRACKET, K.BACKSLASH],
            [K.TAB, K.A, K.S, K.D, K.F, K.G, K.H, K.J, K.K, K.L, K.SEMICOLON, K.QUOTE, K.SPACE, K.ENTER],
            [K.LEFT_SHIFT, K.Z, K.X, K.C, K.V, K.B, K.N, K.M, K.COMMA, K.PERIOD, K.FORWARD_SLASH, (K.HOME, K.END), (K.DELETE, K.CAPS_LOCK), K.RIGHT_SHIFT],
            [K.GRAVE_ACCENT, K.ONE, K.TWO, K.THREE, K.FOUR, K.FIVE, K.SIX, K.SEVEN, K.EIGHT, (K.NINE, K.PAGE_UP), (K.ZERO, K.PAGE_DOWN), K.MINUS, K.EQUALS, (K.BACKSPACE, K.PRINT_SCREEN)],
            [FN, K.WINDOWS, K.LEFT_CONTROL, K.ALT, (K.F1, K.F7), (K.F2, K.F8), (K.F3, K.F9), (K.F4, K.F10), (K.F5, K.F11), (K.F6, K.F12), K.UP_ARROW, K.DOWN_ARROW, (K.LEFT_ARROW, K.PAGE_UP), (K.RIGHT_ARROW, K.PAGE_DOWN)],
        ]
        self.press_buttons = [
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False, False, False, False, False],
        ]
        self.buttons = []
        self.continue_press_buttons = []
        self.release = []

    def press_keys(self, keys = []):
        self.buttons = []
        self.keyboard.press(*keys)
        self.keyboard.release(*keys)
        self.release.clear()

    def scan(self):
        for x in range(14):
            for i in range(14):
                if i == x:
                    self.x_lines[i].value = False # scan x line
                else:
                    self.x_lines[i].value = True # disable other lines
            for y in range(5, -1, -1):
                if self.y_lines[y].value == False: # pressd
                    if self.press_buttons[y][x]: # y,x pressed, already pressed
                        if self.press_buttons[5][0]: # fn pressed
                            if y == 5 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.continue_press_buttons.append(self.keys[y][x][1])
                                else:
                                    self.continue_press_buttons.append(self.keys[y][x])
                        else:
                            if y == 5 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.continue_press_buttons.append(self.keys[y][x][0])
                                else:
                                    self.continue_press_buttons.append(self.keys[y][x])
                    else: # y,x not pressed, first press
                        if self.press_buttons[5][0]: # fn pressed
                            if y == 5 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.buttons.append(self.keys[y][x][1])
                                else:
                                    self.buttons.append(self.keys[y][x])
                        else:
                            if y == 5 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.buttons.append(self.keys[y][x][0])
                                else:
                                    self.buttons.append(self.keys[y][x])
                        self.press_buttons[y][x] = True
                else: # not press
                    if self.press_buttons[y][x]:
                        self.press_buttons[y][x] = False
                        if y == 5 and x == 0:
                            pass
                        else:
                            if isinstance(self.keys[y][x], tuple):
                                if self.keys[y][x][0] in self.buttons:
                                    self.buttons.remove(self.keys[y][x][0])
                                    self.release.append(self.keys[y][x][0])
                                else:
                                    self.buttons.remove(self.keys[y][x][1])
                                    self.release.append(self.keys[y][x][1])
                            else:
                                if self.keys[y][x] in self.buttons:
                                    self.buttons.remove(self.keys[y][x])
                                self.release.append(self.keys[y][x])
        if self.press_buttons[5][0]:
            if K.UP_ARROW in self.buttons:
                self.consumer_control.send(C.VOLUME_INCREMENT)
                self.buttons.remove(K.UP_ARROW)
            elif K.DOWN_ARROW in self.buttons:
                self.consumer_control.send(C.VOLUME_DECREMENT)
                self.buttons.remove(K.DOWN_ARROW)
        if MOUSE_LEFT in self.release:
            self.mouse.click(Mouse.LEFT_BUTTON)
            self.release.remove(MOUSE_LEFT)
        if MOUSE_RIGHT in self.release:
            self.mouse.click(Mouse.RIGHT_BUTTON)
            self.release.remove(MOUSE_RIGHT)
        if MOUSE_UP in self.release:
            self.mouse.move(wheel = 3)
            self.release.remove(MOUSE_UP)
        if MOUSE_DOWN in self.release:
            self.mouse.move(wheel = -3)
            self.release.remove(MOUSE_DOWN)
        if MOUSE_MIDDLE in self.release:
            self.mouse.click(Mouse.MIDDLE_BUTTON)
            self.release.remove(MOUSE_MIDDLE)
        if MOUSE_LEFT in self.continue_press_buttons:
            self.mouse.press(Mouse.LEFT_BUTTON)
            self.continue_press_buttons.remove(MOUSE_LEFT)
        if MOUSE_RIGHT in self.continue_press_buttons:
            self.mouse.press(Mouse.RIGHT_BUTTON)
            self.continue_press_buttons.remove(MOUSE_RIGHT)
        if MOUSE_UP in self.continue_press_buttons:
            self.mouse.move(wheel = 3)
            self.continue_press_buttons.remove(MOUSE_UP)
        if MOUSE_DOWN in self.continue_press_buttons:
            self.mouse.move(wheel = -3)
            self.continue_press_buttons.remove(MOUSE_DOWN)
        if MOUSE_MIDDLE in self.continue_press_buttons:
            self.mouse.press(Mouse.MIDDLE_BUTTON)
            self.continue_press_buttons.remove(MOUSE_MIDDLE)
        try:
            self.keyboard.press(*self.buttons)
            self.keyboard.release(*self.release)
            self.release.clear() # = []
        except Exception as e:
            self.release.clear()
            try:
                self.keyboard.release_all()
            except Exception as e:
                print("release_all keys error: ", e)
            try:
                time.sleep(1)
                self.keyboard = Keyboard(usb_hid.devices)
            except Exception as e:
                print("reinit keyboard error: ", e)
            print(e)


def monitor(task, name, scheduler = None, display_id = None):
    while True:
        gc.collect()
        monitor_msg = "CPU%s:%3d%%  RAM:%3d%%" % (scheduler.cpu, int(100 - scheduler.idle), int(100 - (scheduler.mem_free() * 100 / (264 * 1024))))
        yield Condition(sleep = 2000, send_msgs = [Message({"msg": monitor_msg}, receiver = display_id)])


def display(task, name):
    while True:
        yield Condition(sleep = 0, wait_msg = True)
        msg = task.get_message()
        print(msg.content["msg"])


def keyboard_scan(task, name, interval = 50, display_id = None, mouse = None):
    k = CustomKeyBoard(mouse)
    while True:
        t = ticks_ms()
        try:
            k.scan()
        except Exception as e:
            print(e)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def mouse_scan(task, name, interval = 50, display_id = None, mouse = None):
    x_axis = analogio.AnalogIn(board.A1)
    y_axis = analogio.AnalogIn(board.A0)
    while True:
        t = ticks_ms()
        x = get_level_value(x_axis, negative = -1)
        y = get_level_value(y_axis, negative = -1)
        mouse.move(x = x // 120, y = y // 120)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def brightness_control(task, name, interval = 50, display_id = None):
    light = 10
    light_min = 0
    light_max = 90
    light_pwm = pwmio.PWMOut(board.GP28, frequency = 2000)
    light_up_button = Button(board.GP22, digitalio.Direction.INPUT, digitalio.Pull.UP)
    light_down_button = Button(board.GP21, digitalio.Direction.INPUT, digitalio.Pull.UP)

    def set_light(percent):
        light_pwm.duty_cycle = int((100 - percent) * 65535 / 100)

    set_light(light)
    while True:
        t = ticks_ms()
        if light_up_button.click():
            light += 5
            if light > light_max:
                light = light_max
            print(light)
            set_light(light)
        elif light_down_button.click():
            light -= 5
            if light < light_min:
                light = light_min
            print(light)
            set_light(light)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def led_breath(task, name, interval = 500, display_id = None):
    led = setup_pin(board.GP25, digitalio.Direction.OUTPUT) # breathing light for status checking
    led.value = True
    yield Condition(sleep = interval)
    while True:
        led.value = not led.value
        yield Condition(sleep = interval)


if __name__ == "__main__":
    try:
        s = Scheluder(cpu = 0)
        time.sleep(1)
        mouse = Mouse(usb_hid.devices)
        display_id = s.add_task(Task(display, "display"))
        monitor_id = s.add_task(Task(monitor, "monitor", kwargs = {"scheduler": s, "display_id": display_id}))
        keyboard_id = s.add_task(Task(keyboard_scan, "keyboard", kwargs = {"interval": 50, "display_id": display_id, "mouse": mouse}))
        mouse_id = s.add_task(Task(mouse_scan, "mouse", kwargs = {"interval": 25, "display_id": display_id, "mouse": mouse}))
        # brightness_id = s.add_task(Task(brightness_control, "brightness", kwargs = {"interval": 50, "display_id": display_id}))
        led_id = s.add_task(Task(led_breath, "led", kwargs = {"interval": 500, "display_id": display_id}))
        s.run()
    except Exception as e:
        print("main: %s" % str(e))

