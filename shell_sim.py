#!/usr/bin/env python
# author: Murali Achanta
import re
import sys
import hashlib
import pickle
import string
from cmd2 import Cmd, make_option, options

class simulated_shell(Cmd):
    '''
    SIMULATED_SHELL is a Cmd inherited class to parse Cisco NXOS 
    tac-pac show tech file and provide CLI interface very similar
    to actual device shell
    usage:
        supported commands "show xxx", "test xxx", "debug xxx", "exit "
        "attach module x", "list - display found CLIs for current module"
        "listall - display all CLIs found in the tac-pac file"
        [0][linux myname]$ shell_sim.py sh_tech_details.txt 

         ----
         Welcome to the simulate device shell for tac-pac. 
         ----

        MySwitch-1 # show module
        `show module`
        Mod  Ports  Module-Type                         Model              Status
        ---  -----  ----------------------------------- ------------------ ----------
        1    32     10 Gbps Ethernet Module             N7K-M132XP-12      ok
        2    48     10/100/1000 Mbps Ethernet Module    N7K-M148GT-11      ok
        5    0      Supervisor module-1X                N7K-SUP1           active *
        6    0      Supervisor module-1X                N7K-SUP1           ha-standby
    '''
    Cmd.prompt = "(switch)# "

    def __init__(self, *args, **kwargs):        
        Cmd.__init__(self, *args, **kwargs)
        self.intro = '''\
        \n ----\n Welcome to the NXOS type shell for tac-pac. \
        \n ----\n'''

        self.file = '/tmp/nxos_shell'
        # build time lists
        self.all_module_cmds = [[] for i in xrange(20)]
        self.offset_tuple_list = [[] for i in xrange(20)]
        self.module_s_list = []
        self.module_e_list = []
        #run time locals
        self.local_mod = []
        self.s=[]
        self.cmd_dict = {}
        self.attach_mod_dict = {}
        
    def _delete_unwanted(self):
        del self.all_module_cmds
        del self.module_e_list
        del self.module_s_list
        del self.offset_tuple_list

    def _set_prompt(self):
        '''
        set swtich name based on "show switchname" command output
        '''
        d,fw = self._find_command('show switchname', self.cmd_mod_dict)
        try:
            if d['EOL']:
                with open(self.file, 'r') as f:
                    start,end=d['EOL'][0]
                    f.seek(start)
                    s = f.readline()
                    s = f.readline()
                    Cmd.prompt = s.rstrip('\r\n')+'# '
        except KeyError, ValueError:
            return

    def _compute_sha1_hash(self):
        '''
        compute hash for the current tac-pac file to check if something
        changed in the content
        '''
        try:
            BUF_SIZE = 65536
            sha1 = hashlib.sha1()
            with open(self.file, 'rb') as f:
                while True:
                    data = f.read(BUF_SIZE)
                    if not data:
                        break
                    sha1.update(data)
            return str(sha1.hexdigest())
        except IOError:
            return None
            
    def _parse_tac_file(self):
        '''
        Parses the TAC_PAC file for list of commands and module
        '''
        def update_tuple_list(offsets, module):
            for i in range(len(offsets)-1):
                self.offset_tuple_list[module].append((offsets[i], offsets[i+1],))
        match_module_start = re.compile('''.*########################\
 Start of output for module (.*) ####################.*''')
        match_module_end = re.compile('''.*########################\
 End of output for module (.*) ####################.*''')
        match_cmd = re.compile('.*\`([A-Za-z\s\-_0-9:\/\\\|\"\']+)\`')
        offset = 0
        offsets = []
        reading_for_mod = 0
        f = open(self.file, 'r')
        for line in f:
            match_obj = match_cmd.match(line)
            mod_start_obj = match_module_start.match(line)
            mod_end_obj = match_module_end.match(line)
            if mod_start_obj:
                offsets.append(offset-1)
                update_tuple_list(offsets, reading_for_mod)
                s = mod_start_obj.group(1)
                if self.module_s_list.count(s) == 0:
                    self.module_s_list.append(s)
                reading_for_mod = int(s)
                offsets = []
            if mod_end_obj:
                e = mod_end_obj.group(1)
                if self.module_e_list.count(e) == 0:
                    self.module_e_list.append(e)
                offsets.append(offset-1)
                update_tuple_list(offsets, reading_for_mod)
                reading_for_mod = 0
                offsets = []
            if match_obj:
                offsets.append(offset)
                self.all_module_cmds[reading_for_mod].append(match_obj.group(1).strip())
            offset += len(line)
        f.close()
        #append last offset for modules
        offsets.append(offset-1)
        update_tuple_list(offsets, reading_for_mod)
        if len(self.module_s_list) != len(self.module_e_list):
            print 'Warning command list might not be' \
                'accurate due to in correct module' \
                'start and end comments'
        # default set context to module 0
        self.local_mod.append(0)

    def _display_output(self, start, end):
        '''
        internal method display output using Cmd class poutput method
        '''
        display_file = open(self.file, 'r')
        display_file.seek(start)
        try:
            filtered_string = ''.join(s for s in display_file.read(end - start) if s in string.printable)
            self.poutput(filtered_string)
        except IOError:
            pass

    def _get_command(self, arg, opts=None, first_token=None):
        '''
        main function for all commands with first_token 
        (eg "show ", "test ", "debug ")
        '''
        trimmed_arg = ' '.join(arg.split())
        trimmed_arg = trimmed_arg.strip(' EOL')
        d,fw = self._find_command(first_token+' '+trimmed_arg, self.cmd_mod_dict)
        found_words = len(fw)-1
        if found_words != len(trimmed_arg.split()):
            print(' %r are not valid keywords' % trimmed_arg.split()[found_words:])
            return
        try:
            for start, end in d['EOL']:
                self._display_output(start,end)
        except KeyError:
            print('not complete command, possible words %s' % d.keys())

    def build_cmd_data_items(self):
        '''
        build data items from pickle file 
        if no pickle file found, rebuild one
        and save to /tmp directory
        file name is {hash_value}.pcl
        '''
        pickle_file_name = '/tmp/'+self._compute_sha1_hash()+'.pcl'
        try:
            with open(pickle_file_name, 'rb') as f:
                print('<< using cache file {} >>'.format(pickle_file_name))
                data = pickle.load(f)
                (self.cmd_dict, self.attach_mod_dict) = data
            # default set context to module 0
            self.cmd_mod_dict = self.cmd_dict['module_0']
            self.local_mod.append(0)
            self._set_prompt()
            self._delete_unwanted()
            return
        except IOError:
            pass
        print('<< building cache file {} >>'.format(pickle_file_name))
        self._parse_tac_file()
        self._build_parser_dicts()
        self._set_prompt()
        with open(pickle_file_name, 'wb') as f:
            data = (self.cmd_dict, self.attach_mod_dict)
            pickle.dump(data, f)
        self._delete_unwanted()

    def do_attach(self, arg, opts=None):
        ''' attach to module x for module context commands'''
        old_prompt = Cmd.prompt
        trimmed_arg = ' '.join(arg.split())
        arg = trimmed_arg.strip(' EOL')        
        Cmd.prompt = Cmd.prompt+'('+arg+')'+'# '
        get_mod = re.compile('module (.*)')
        mod_num_obj = get_mod.match(arg)
        if mod_num_obj:
            key_name = 'module_{}'.format(mod_num_obj.group(1))
            if key_name not in self.cmd_dict.keys() or not self.cmd_dict[key_name]:
                print arg, "not present"
            else:
                slot = int(mod_num_obj.group(1))
                self.cmd_mod_dict = self.cmd_dict['module_{}'.format(slot)]
                self.local_mod.append(slot)
                self.cmdloop()
                self.local_mod.pop()
                old_slot = self.local_mod[-1]
                self.cmd_mod_dict = self.cmd_dict['module_{}'.format(old_slot)]
        Cmd.prompt = old_prompt

    def do_debug(self, arg, opts=None):
        ''' debug xxx commands in current file'''
        self._get_command(arg, opts, first_token='debug ')

    def _print_dict(self, d, prefix=None):
        if isinstance(d, list):
            if prefix:
                self.poutput(prefix+' '.join(self.s).strip('EOL'))
            else:
                self.poutput(' '.join(self.s).strip('EOL'))
            return
        for key in d.keys():
            self.s.append(key)
            self._print_dict(d[key], prefix)
            self.s.pop()

    def do_listall(self, arg):
        ''' list all commands in file'''
        self.s=[]
        for mod in xrange(18):
            key = 'module_{}'.format(mod)
            prefix='[{}] -> '.format(key)
            self._print_dict(self.cmd_dict[key], prefix)

    def do_list(self, arg):
        ''' list all local commands under current module context'''
        self.s=[]
        self._print_dict(self.cmd_mod_dict)

    def do_show(self, arg, opts=None):
        ''' show xxx commands in current file'''
        self._get_command(arg, opts, first_token='show ')

    def do_sh(self, arg, opts=None):
        ''' show xxx commands in current file'''
        self._get_command(arg, opts, first_token='sh ')

    def do_slot(self, arg, opts=None):
        ''' show xxx commands in current file'''
        self._get_command(arg, opts, first_token='slot ')

    def do_test(self, arg, opts=None):
        ''' test xxx commands in current file'''
        self._get_command(arg, opts, first_token='test ')
    
    def _complete_command(self, text, line, begidx, endidx, cmds):
        ''' method for TAB completion on all commands '''
        word_to_complete = line[begidx:endidx]
        trimmed_line = ' '.join(line.split())
        d,fw = self._find_command(trimmed_line, cmds)
        l = [k for k in d.keys() if k.startswith(word_to_complete)]
        if len(l)==1 and l[0] != 'EOL':
            l[0] = l[0]+' '
            return l
        else:
            if word_to_complete and not l:
                return l
            if l:
                return l
            return map(lambda s:s+' ',sorted(list(d.keys())))

    def complete_show(self, text, line, begidx, endidx):
        ''' method for TAB completion on show command '''
        return self._complete_command(text, line, begidx, endidx, self.cmd_mod_dict)

    def complete_sh(self, text, line, begidx, endidx):
        ''' method for TAB completion on show command '''
        return self._complete_command(text, line, begidx, endidx, self.cmd_mod_dict)

    def complete_slot(self, text, line, begidx, endidx):
        ''' method for TAB completion on show command '''
        return self._complete_command(text, line, begidx, endidx, self.cmd_mod_dict)
    
    def complete_debug(self, text, line, begidx, endidx):
        ''' method for TAB completion on debug command '''
        return self._complete_command(text, line, begidx, endidx, self.cmd_mod_dict)
    
    def complete_test(self, text, line, begidx, endidx):
        ''' method for TAB completion on test command '''
        return self._complete_command(text, line, begidx, endidx, self.cmd_mod_dict)
    
    def complete_attach(self, text, line, begidx, endidx):
        ''' method for TAB completion on attach command '''
        return self._complete_command(text, line, begidx, endidx, self.attach_mod_dict)
    
    def default(self, *args, **kwargs):
        ''' method for unknown commands '''
        line = ''.join(args[0].split())
        trimmed_file = ''.join(self.file.split())
        if (trimmed_file.upper() != line.upper()):
            print "unknown commad: {} {}".format(args,kwargs)

    def _make_dict(self, cmd, loc, d):
        ''' make nested dict for a given command '''
        for word in cmd.split():
            if word not in d.keys():
                d[word] = {}
            d = d[word]
        try:
            d['EOL'].append(loc)
        except KeyError:
            d['EOL']=[loc]

    def _build_parser_dicts(self):
        ''' build module level cmds nested dict with EOLs '''
        for mod_num, cmds in enumerate(self.all_module_cmds):
            item_name = 'module_{}'.format(mod_num)
            self.cmd_dict[item_name]={}
            d = self.cmd_dict[item_name]
            locs = self.offset_tuple_list[mod_num]
            for i, cmd in enumerate(cmds):
                self._make_dict(cmd, locs[i], d)
        # set defaults
        self.cmd_mod_dict = self.cmd_dict['module_0']
        for mod in self.module_s_list:
            self._make_dict('attach module {}'.format(mod), (0,0), self.attach_mod_dict)

    def _find_command(self, cmd, d):
        ''' traverse nested dict to get the command offest
        >>> t=self._find_command('show version', cmd_d)
        >>> t
        {'EOL': [(70251805, 70252138)]}
        '''
        found_words=[]
        for word in cmd.split():
            if d and word in d.keys():
                found_words.append(word)
                d=d[word]
        return d, found_words

    def redirect_output(self, statement):
        skip_more = ('attach', 'py',)
        if statement.parsed.command not in skip_more:
            if not statement.parsed.pipeTo and not statement.parsed.output:
                statement.parsed.pipeTo='more'
        return Cmd.redirect_output(self, statement)
    
if __name__ == '__main__':
    c = simulated_shell()
    if len(sys.argv) <= 1:
        print ">>>> usage: {} <uncompressed tac-pac filename>".format(sys.argv[0])
        print c.__doc__
        exit()
    c.file = sys.argv[1]
    c.build_cmd_data_items()
    c.cmdloop()
