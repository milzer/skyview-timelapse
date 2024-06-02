import re
import argparse
import contextlib
import pathlib
import struct
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

BROWSERS = {
    'chrome': (webdriver.Chrome, webdriver.ChromeService, webdriver.ChromeOptions),
    'firefox': (webdriver.Firefox, webdriver.FirefoxService, webdriver.FirefoxOptions),
    'edge': (webdriver.Edge, webdriver.EdgeService, webdriver.EdgeOptions),
    'safari': (webdriver.Safari, webdriver.SafariService, webdriver.SafariOptions),
}

CAMERAS = (
    'teletorn',
    'kohtlanomme',
    'pärnu',
    'tartu',
    'orissaare',
    'valgjarve',
)

def create_driver(browser: str, window_size: Tuple[int, int], driver_path: Optional[str] = None) -> webdriver.Remote:
    try:
        driverclass, serviceclass, optionsclass = BROWSERS[browser]
        options = optionsclass()  # type: ignore
        options.add_argument('--headless')
        size_str = ','.join(map(str, window_size))
        options.add_argument(f'--window-size={size_str}')
        service = serviceclass(executable_path=driver_path)  # type: ignore
        driver = driverclass(service=service, options=options)  # type: ignore
        return driver
    except IndexError as e:
        raise LookupError(f'No browser found: {browser}') from e


def choose_driver(window_size: Tuple[int, int]) -> webdriver.Remote:
    for browser in BROWSERS:
        with contextlib.suppress(WebDriverException):
            return create_driver(browser, window_size)

    raise LookupError('No supported browser found')


def time2seconds(s: str) -> int:
    try:
        result = re.match(r'^(\d+)([mhs])$', s)
        number = int(result.group(1))  # type: ignore
        unit = result.group(2)  # type: ignore
    except Exception as e:
        raise ValueError('Invalid time format') from e

    if unit == 'h':
        return number * 3600
    elif unit == 'm':
        return number * 60
    else:
        return number


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--browser', choices=BROWSERS.keys(), nargs='?', default=None)
    parser.add_argument('-c', '--camera', choices=CAMERAS, default=CAMERAS[0])
    parser.add_argument('-s', '--window-size', nargs=2, type=int, default=(1920, 1080))
    parser.add_argument('-d', '--driver-path', type=pathlib.Path, default=None)
    parser.add_argument('-i', '--interval', type=int, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-n', '--num-screenshots', type=int)
    group.add_argument('-t', '--time', type=time2seconds)
    args = parser.parse_args()

    if args.browser:
        driver = create_driver(args.browser, args.window_size, args.driver_path)
    else:
        driver = choose_driver(args.window_size)

    try:
        driver.get('https://skyview.ee')

        time.sleep(5)

        cookie_accept = driver.find_element(By.ID, 'cookie_action_close_header')
        cookie_accept.click()

        player = driver.find_element(By.ID, f'player-{args.camera}')
        driver.execute_script(
            "arguments[0].classList.remove('jw-flag-user-inactive'); arguments[0].classList.add('jw-flag-fullscreen');",
            player,
        )

        play = player.find_element(By.CSS_SELECTOR, "[aria-label='Play']")
        actions = webdriver.ActionChains(driver)
        actions.move_to_element(play)
        play.click()

        time.sleep(1)

        # Check if we need to resize the window

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / 'sizetest.png'
            player.screenshot(str(path))
            with path.open('rb') as tmpfile:
                head = tmpfile.read(24)
                actual_width, actual_height = struct.unpack('>ii', head[16:24])
                width_diff = args.window_size[0] - actual_width
                height_diff = args.window_size[1] - actual_height
                if width_diff or height_diff:
                    print(f'Resizing window by {width_diff}x{height_diff}')
                    driver.set_window_size(args.window_size[0] + width_diff, args.window_size[1] + height_diff)
                    time.sleep(1)

        starttime = datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M')
        screenshots_dir = pathlib.Path(f'{args.camera}_{starttime}')
        screenshots_dir.mkdir(exist_ok=False)

        if args.num_screenshots:
            num_screenshots = args.num_screenshots
        else:
            num_screenshots = int(args.time / args.interval)

        digits = len(str(num_screenshots))

        for i in range(num_screenshots):
            screenshot_path = screenshots_dir / f'{i:0{digits}d}.png'
            player.screenshot(str(screenshot_path))
            print(f'Saved {screenshot_path}')
            time.sleep(args.interval)

        # TODO: run ffmpeg or provide a sample command line

    finally:
        driver.quit()
