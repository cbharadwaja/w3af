'''
rnd_case.py

Copyright 2006 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

'''

from core.controllers.plugins.evasion_plugin import EvasionPlugin
from core.controllers.w3afException import w3afException
from core.data.url.HTTPRequest import HTTPRequest as HTTPRequest
from core.data.parsers.url import parse_qs

# options
from core.data.options.option import option
from core.data.options.option_list import OptionList

from random import choice, randint


class rnd_case(EvasionPlugin):
    '''
    Change the case of random letters.
    @author: Andres Riancho (andres.riancho@gmail.com)
    '''

    def __init__(self):
        EvasionPlugin.__init__(self)

    def modifyRequest(self, request ):
        '''
        Mangles the request
        
        @parameter request: HTTPRequest instance that is going to be modified by the evasion plugin
        @return: The modified request
        
        >>> from core.data.parsers.url import URL
        >>> rc = rnd_case()
        
        >>> u = URL('http://www.w3af.com/')
        >>> r = HTTPRequest( u )
        >>> rc.modifyRequest( r ).url_object.url_string
        u'http://www.w3af.com/'

        >>> u = URL('http://www.w3af.com/ab/')
        >>> r = HTTPRequest( u )
        >>> rc.modifyRequest( r ).url_object.getPath() in ['/ab/','/aB/','/Ab/','/AB/']
        True

        >>> u = URL('http://www.w3af.com/')
        >>> r = HTTPRequest( u, data='a=b' )
        >>> rc.modifyRequest( r ).get_data() in ['a=b','A=b','a=B','A=B']
        True

        >>> u = URL('http://www.w3af.com/a/B')
        >>> r = HTTPRequest( u )
        >>> options = ['/a/b','/a/B','/A/b','/A/B'] 
        >>> path = rc.modifyRequest( r ).url_object.getPath()
        >>> path in options
        True

        >>> #
        >>> #    The plugins should not modify the original request
        >>> #
        >>> u.url_string
        u'http://www.w3af.com/a/B'

        '''
        # First we mangle the URL        
        path = request.url_object.getPath()
        path = self._mutate(path)
        
        # Finally, we set all the mutants to the request in order to return it
        new_url = request.url_object.copy()
        new_url.setPath( path )
        
        # Mangle the postdata
        data = request.get_data()
        if data:
            
            try:
                # Only mangle the postdata if it is a url encoded string
                parse_qs( data )
            except:
                pass
            else:
                data = self._mutate(data) 
        
        new_req = HTTPRequest( new_url , data, request.headers, 
                               request.get_origin_req_host() )
        
        return new_req
    
    def _mutate( self, data ):
        '''
        Change the case of the data string.
        @return: a string.
        '''
        new_data = ''
        for char in data:
            if randint(1, 2) == 2:
                char = char.upper()
            else:
                char = char.lower()
            new_data += char
        return new_data
        
    def get_options( self ):
        '''
        @return: A list of option objects for this plugin.
        '''    
        ol = OptionList()
        return ol

    def set_options( self, option_list ):
        '''
        This method sets all the options that are configured using the user interface 
        generated by the framework using the result of get_options().
        
        @parameter OptionList: A dictionary with the options for the plugin.
        @return: No value is returned.
        ''' 
        pass
        
    def get_plugin_deps( self ):
        '''
        @return: A list with the names of the plugins that should be run before the
        current one.
        '''        
        return []

    def getPriority( self ):
        '''
        This function is called when sorting evasion plugins.
        Each evasion plugin should implement this.
        
        @return: An integer specifying the priority. 100 is run first, 0 last.
        '''
        return 25
    
    def get_long_desc( self ):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        This evasion plugin changes the case of random letters.
        
        Example:
            Input:      '/bar/foo.asp'
            Output :    '/BAr/foO.Asp'
        '''
