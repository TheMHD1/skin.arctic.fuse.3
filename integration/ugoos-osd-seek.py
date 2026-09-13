"""Fixed +/-30-second arrow seeks only on Arctic Fuse 3's video timeline."""
import sys
import xbmc


def action_for(is_arctic, is_osd, is_timeline, is_video, direction='right'):
    if direction not in ('left', 'right'):
        raise ValueError('Unsupported direction')
    if is_arctic and is_osd and is_timeline and is_video:
        return 'Seek(-30)' if direction == 'left' else 'Seek(30)'
    return 'Action(Left)' if direction == 'left' else 'Action(Right)'


if __name__ == '__main__':
    action = action_for(
        xbmc.getSkinDir() == 'skin.arctic.fuse.3',
        xbmc.getCondVisibility('Window.IsActive(videoosd)'),
        xbmc.getCondVisibility('Control.HasFocus(8200)'),
        xbmc.getCondVisibility('Player.HasVideo'),
        sys.argv[1] if len(sys.argv) > 1 else 'right',
    )
    xbmc.executebuiltin(action)
