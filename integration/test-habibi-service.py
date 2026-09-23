import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT=Path(__file__).resolve().parent/'plugin.video.habibi.resume'


def load_service():
    xbmc=types.ModuleType('xbmc')
    xbmc.Monitor=object
    xbmc.getCondVisibility=lambda condition:False
    xbmcgui=types.ModuleType('xbmcgui')
    with mock.patch.dict(sys.modules,{'xbmc':xbmc,'xbmcgui':xbmcgui}):
        spec=importlib.util.spec_from_file_location('habibi_service_test',ROOT/'service.py')
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module,xbmc


class ServiceTests(unittest.TestCase):
    def test_event_grace_survives_earlier_entry_refresh(self):
        service,_=load_service()
        # Entering the hub may refresh immediately, but it is not the scheduled
        # post-stop refresh and therefore must not clear due.
        self.assertEqual(service.refresh_decision(True,False,10,0,12),(True,False))
        self.assertEqual(service.refresh_decision(True,True,12,10,12),(True,True))
        self.assertEqual(service.refresh_decision(False,True,12,0,12),(False,True))

    def test_notifications_extend_due_and_clock_is_monotonic(self):
        service,_=load_service()
        monitor=service.Monitor()
        with mock.patch.object(service.time,'monotonic',side_effect=[10,11,12]):
            monitor.onNotification('player','Player.OnStop','{}')
            monitor.onNotification('library','VideoLibrary.OnUpdate','{}')
            monitor.onNotification('other','Unrelated','{}')
        self.assertEqual(monitor.due,15)
        clock=service.RefreshClock()
        with mock.patch.object(service.time,'monotonic_ns',side_effect=[100,90,90]):
            self.assertEqual([clock.next(),clock.next(),clock.next()],['100','101','102'])

    def test_home_and_arctic_videos_hub_are_recognized(self):
        service,xbmc=load_service()
        xbmc.getCondVisibility=lambda condition:condition=='Window.IsActive(videos)'
        self.assertTrue(service.home_hub_active())
        xbmc.getCondVisibility=lambda condition:condition=='Window.IsActive(home)'
        self.assertTrue(service.home_hub_active())
        xbmc.getCondVisibility=lambda condition:False
        self.assertFalse(service.home_hub_active())


if __name__=='__main__':unittest.main()
