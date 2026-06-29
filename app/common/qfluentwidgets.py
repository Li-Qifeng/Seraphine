'''
PyQt-Fluent-Widgets without Ads.
'''

import sys

sys.stdout = None
from qfluentwidgets import *  # noqa: E402
from qfluentwidgets.components.widgets.line_edit import CompleterMenu, LineEditButton  # noqa: E402
from qfluentwidgets.common.animation import BackgroundAnimationWidget  # noqa: E402
from qfluentwidgets.common.animation import BackgroundColorObject  # noqa: E402
from qfluentwidgets.window.fluent_window import FluentWindowBase  # noqa: E402
from qfluentwidgets.window.stacked_widget import StackedWidget  # noqa: E402
from qfluentwidgets.components.widgets.frameless_window import FramelessWindow  # noqa: E402
from qframelesswindow import SvgTitleBarButton  # noqa: E402
sys.stdout = sys.__stdout__
