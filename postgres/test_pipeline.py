from decimal import Decimal
import pytest
from pipeline import number,validate_table,digest

@pytest.mark.parametrize('text,expected',[('18,355',Decimal(18355)),('-4.25',Decimal('-4.25')),('1990 - 2002',None),('1,23',None),('5%',None),('',None)])
def test_numbers(text,expected): assert number(text)==expected
def test_duplicate_headers_unicode_links():
    validate_table('test',{'header':[['Name',[]],['Name',[]]],'data':[[['é東京',['/wiki/A','/wiki/B']],['',[]]]]})
def test_ragged_rejected():
    with pytest.raises(ValueError): validate_table('test',{'header':[['x',[]]],'data':[[]]})
def test_filename_safe():
    a=digest('"Weird_Al"_Yankovic_0'.encode()); assert len(a)==64 and a.isalnum()
