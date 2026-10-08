"""The rendered Home predicate, not only its intended Python truth table."""
import hashlib,itertools,re,unittest
from unittest.mock import patch
import overlay

def evaluate(predicate,values):
    for token,value in sorted(values.items(),key=lambda x:-len(x[0])):
        predicate=predicate.replace(token,'1' if value else '0')
    tokens=re.findall(r'[01\[\]+|!]',predicate)
    if ''.join(tokens)!=predicate.replace(' ',''):raise ValueError('Unknown predicate token')
    index=0
    def primary():
        nonlocal index
        token=tokens[index];index+=1
        if token=='!':return not primary()
        if token=='[':
            result=union()
            if tokens[index]!=']':raise ValueError('Unbalanced predicate')
            index+=1;return result
        if token not in ('0','1'):raise ValueError('Invalid predicate')
        return token=='1'
    def intersection():
        nonlocal index
        result=primary()
        while index<len(tokens) and tokens[index]=='+':
            index+=1;right=primary();result=result and right
        return result
    def union():
        nonlocal index
        result=intersection()
        while index<len(tokens) and tokens[index]=='|':
            index+=1;right=intersection();result=result or right
        return result
    result=union()
    if index!=len(tokens):raise ValueError('Trailing predicate')
    return result

class Tests(unittest.TestCase):
    def test_all_32_actual_predicates_keep_transport_and_toggle(self):
        keys=('!String.IsEmpty(Skin.String(HomeSwitcher.1107.Toggle))',
              'Skin.String(HomeSwitcher.1107.Name,Venom TV)',
              'System.HasAddon(plugin.video.venom.tv)','System.HasPVRAddon','PVR.HasTVChannels')
        for bits in itertools.product((False,True),repeat=5):
            with self.subTest(bits=bits):
                self.assertEqual(evaluate(overlay.NEW,dict(zip(keys,bits))),overlay.enabled(*bits))
    def test_exact_single_param_edit_preserves_other_home_routes(self):
        source=('<includes><include name="Home_ControlList_Item_1107"><include content="Home_ControlList_Item">'
            '<param name="enabled">'+overlay.OLD+'</param><param name="action">ReplaceWindow(1107)</param>'
            '</include></include><include name="other">Movies</include></includes>').encode()
        with patch.object(overlay,'BEFORE',hashlib.sha256(source).hexdigest()):
            result=overlay.transform(source)
            self.assertEqual(result,source.replace(overlay.OLD.encode(),overlay.NEW.encode()))
            with self.assertRaises(ValueError):overlay.transform(result)
    def test_unknown_bytes_and_duplicate_anchor_refuse(self):
        with self.assertRaises(ValueError):overlay.transform(b'unknown')
        source=(overlay.OLD+' '+overlay.OLD).encode()
        with patch.object(overlay,'BEFORE',hashlib.sha256(source).hexdigest()):
            with self.assertRaises(ValueError):overlay.transform(source)

if __name__=='__main__':unittest.main()
