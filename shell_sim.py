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
        self.all_module_cmds = [[], [], [], [], [], [], [],
                           [], [], [], [], [], [], [],
                           [], [], [], [], []]
        self.all_module_offsets = [[], [], [], [], [], [], [],
                              [], [], [], [], [], [], [],
                              [], [], [], [], []]
        self.module_repeat_list = [[], [], [], [], [], [], [],
                              [], [], [], [], [], [], [],
                              [], [], [], [], []]        
        self.module_s_list = []
        self.module_e_list = []
        self.cmds = []
        self.line_offset = []
        self.local_mod = []

    def _set_prompt(self):
        '''
        set swtich name based on "show switchname" command output
        '''
        try:
            index = self.cmds.index("show switchname")
        except ValueError:
            return
        if index is not None:
            with open(self.file, 'r') as f:
                f.seek(self.line_offset[index])
                s = f.readline()
                s = f.readline()
                Cmd.prompt = s.rstrip('\r\n')+'# '

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
        match_module_start = re.compile('''.*########################\
 Start of output for module (.*) ####################.*''')
        match_module_end = re.compile('''.*########################\
 End of output for module (.*) ####################.*''')
        match_cmd = re.compile('.*\`([A-Za-z\s\-_0-9:\/\\\|\"\']+)\`')
        offset = 0
        reading_for_mod = 0
        f = open(self.file, 'r')
        for line in f:
            match_obj = match_cmd.match(line)
            mod_start_obj = match_module_start.match(line)
            mod_end_obj = match_module_end.match(line)
            if mod_start_obj:
                s = mod_start_obj.group(1)
                if self.module_s_list.count(s) == 0:
                    self.module_s_list.append(s)
                reading_for_mod = int(s)
            if mod_end_obj:
                e = mod_end_obj.group(1)
                if self.module_e_list.count(e) == 0:
                    self.module_e_list.append(e)
                self.module_repeat_list[reading_for_mod].append(offset)
                reading_for_mod = 0
            if match_obj:
                self.line_offset.append(offset)
                self.cmds.append(match_obj.group(1).strip())
                self.all_module_cmds[reading_for_mod].append(match_obj.group(1).strip())
                self.all_module_offsets[reading_for_mod].append(offset)
            offset += len(line)
        f.close()
        #append last offset for modules
        self.line_offset.append(offset)
        for i, entry in enumerate(self.module_repeat_list):
            if entry:
                self.all_module_offsets[i].append(entry[-1])
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
        look_for = re.compile(first_token+trimmed_arg+".*")
        multiple_cmds = 0
        provided_word_count = len(trimmed_arg.split()) + 1
        skip_multi_prompt = 0
        full_match_cmd_list = []
        # loop thru all commands
        index = 0
        for line in self.cmds:
            found = look_for.match(line)
            if found:
                multiple_cmds = multiple_cmds+1
                words = line.split()
                # check if we have complete command match 
                if provided_word_count == len(words):
                    skip_multi_prompt = 1
                    full_match_cmd_list.append(index)
            index = index + 1
        if multiple_cmds > 1 and skip_multi_prompt == 0:
            print ">>>>>>multipe 'show", arg, "'; multiple commands =",multiple_cmds, "found<<<<<<"
            return
        my_index = self.cmds.index(first_token+trimmed_arg)
        for i in full_match_cmd_list:
            ds = self.line_offset[i]
            de = self.line_offset[i+1]-1
            self._display_output(ds, de)

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
                (self.all_module_cmds, self.all_module_offsets,
                 self.module_repeat_list,
                 self.module_s_list, self.module_e_list, 
                 self.cmds, self.line_offset) = data
            # default set context to module 0
            self.local_mod.append(0)
            self._set_prompt()
            return
        except IOError:
            pass
        print('<< building cache file {} >>'.format(pickle_file_name))
        self._parse_tac_file()
        self._set_prompt()
        with open(pickle_file_name, 'wb') as f:
            data = (self.all_module_cmds, 
                    self.all_module_offsets,
                    self.module_repeat_list,
                    self.module_s_list, 
                    self.module_e_list, 
                    self.cmds, 
                    self.line_offset)
            pickle.dump(data, f)

    def do_attach(self, arg, opts=None):
        ''' attach to module x for module context commands'''
        old_prompt = Cmd.prompt
        Cmd.prompt = Cmd.prompt+'('+arg+')'+'# '
        get_mod = re.compile('module (.*)')
        mod_num_obj = get_mod.match(arg)
        if mod_num_obj:
            if self.module_s_list.count(mod_num_obj.group(1)) == 0:
                print arg, "not present"
            else:
                slot = int(mod_num_obj.group(1))
                self.cmds = self.all_module_cmds[slot]
                self.line_offset = self.all_module_offsets[slot]
                self.local_mod.append(slot)
                self.cmdloop()
                self.local_mod.pop()
                mod_index = self.local_mod[-1]
                self.cmds = self.all_module_cmds[mod_index]
                self.line_offset = self.all_module_offsets[mod_index]
        Cmd.prompt = old_prompt

    def do_debug(self, arg, opts=None):
        ''' debug xxx commands in current file'''
        self._get_command(arg, opts, first_token='debug ')

    def do_listall(self, arg):
        ''' list all commands in file'''
        lines = []
        for m_idx, mod_cmds in enumerate(self.all_module_cmds):
            for cmd in mod_cmds:
                lines.append('[Module {}] -> {}'.format(m_idx, cmd))
        try:
            self.poutput('\n'.join(lines))
        except IOError:
            pass

    def do_list(self, arg):
        ''' list all local commands under current module context'''
        mod_index = self.local_mod[-1]
        print '\n'.join(self.all_module_cmds[mod_index])

    def do_show(self, arg, opts=None):
        ''' show xxx commands in current file'''
        self._get_command(arg, opts, first_token='show ')

    def do_test(self, arg, opts=None):
        ''' test xxx commands in current file'''
        self._get_command(arg, opts, first_token='test ')
    
    def _complete_command(self, text, line, begidx, endidx, cmds):
        ''' method for TAB completion on all commands '''
        completions = []
        word_to_complete = line[begidx:endidx]
        trimmed_line = ' '.join(line.split())        
        look_for = re.compile(trimmed_line+'.*')
        for new_line in cmds:
            if look_for.match(new_line):
                provided_word_count = len(line.split())
                words = new_line.split()
                if word_to_complete == '':
                    completions.append(words[provided_word_count])
                else:
                    completions.append(words[provided_word_count-1])
        if line[begidx-1] == '-':
            c_set = list(set(completions))
            if len(c_set) == 1:
                l = []
                l.append(c_set[0].split('-')[1])
                return l
        rl = list(set(completions))
        if len(rl) == 1:
            rl[0] = rl[0]+' '
        return rl
    
    def complete_show(self, text, line, begidx, endidx):
        ''' method for TAB completion on show command '''
        return self._complete_command(text, line, begidx, endidx, self.cmds)
    
    def complete_debug(self, text, line, begidx, endidx):
        ''' method for TAB completion on debug command '''
        return self._complete_command(text, line, begidx, endidx, self.cmds)
    
    def complete_test(self, text, line, begidx, endidx):
        ''' method for TAB completion on test command '''
        return self._complete_command(text, line, begidx, endidx, self.cmds)
    
    def complete_attach(self, text, line, begidx, endidx):
        ''' method for TAB completion on attach command '''
        attach_cmds = [ 'attach module '+m for m in self.module_s_list]
        return self._complete_command(text, line, begidx, endidx, attach_cmds)
    
    def default(self, *args, **kwargs):
        ''' method for unknown commands '''
        line = ''.join(args[0].split())
        trimmed_file = ''.join(self.file.split())
        if (trimmed_file.upper() != line.upper()):
            print "unknown commad: {} {}".format(args,kwargs)

if __name__ == '__main__':
    c = simulated_shell()
    if len(sys.argv) <= 1:
        print ">>>> usage: {} <uncompressed tac-pac filename>".format(sys.argv[0])
        print c.__doc__
        exit()
    c.file = sys.argv[1]
    c.build_cmd_data_items()
    c.cmdloop()
