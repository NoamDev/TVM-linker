import re
import os

def getFunctions():
	global functions
	for l in lines:
		match = re.search(r"Function (\S+)_external\s+: id=([0-9A-F]+), .*", l);
		if match:
			functions[match.group(1)] = match.group(2)
			# print match.group(1), match.group(2) 
	
def getExitCode():
	for l in lines:
		# print l
		match = re.match(r"TVM terminated with exit code (\d+)", l);
		if match:
			return int(match.group(1))
	assert False
	return -1
	
def getContractAddress():
	for l in lines:
		# print l
		match = re.match(r"Saved contract to file (.*)\.tvc", l);
		if match:
			return match.group(1)
	assert False
	return -1
	
def getStack():
	stack = []
	b = False
	for l in lines:
		if l == "--- Post-execution stack state ---------": 
			b = True
		elif l == "----------------------------------------":
			b = False
		elif b:
			ll = l.replace("Reference to ", "")
			stack.append(ll)
	return " ".join(stack)
		
def cleanup():
	if CONTRACT_ADDRESS:
		os.remove(CONTRACT_ADDRESS + ".tvc")

CONTRACT_ADDRESS = None

def compile1(source_file, lib_file):
	cleanup()
	global lines, functions, CONTRACT_ADDRESS
	print("Compiling " + source_file + "...")
	lib = "--lib " + lib_file if lib_file else ""
	cmd = "./target/debug/tvm_linker compile ./tests/{} {} --debug > compile_log.tmp".format(source_file, lib)
	# print cmd
	ec = os.system(cmd)
	if ec != 0:
		error("COMPILATION FAILED!")

	lines = [l.rstrip() for l in open("compile_log.tmp").readlines()]
	# os.remove("compile_log.tmp")

	functions = dict()
	getFunctions()
	CONTRACT_ADDRESS = getContractAddress()

def compile2(source_name):
	cleanup()
	global lines, functions, CONTRACT_ADDRESS
	print("Compiling " + source_name + "...")
	lib_file = "stdlib_sol.tvm"
	source_file = "./tests_sol/{}.code".format(source_name)
	abi_file = "./tests_sol/{}.abi.json".format(source_name)
	
	cmd = "./target/debug/tvm_linker compile {} --abi-json {} --lib {} --debug > compile_log.tmp"
	cmd = cmd.format(source_file, abi_file, lib_file)
	# print cmd
	ec = os.system(cmd)
	if ec != 0:
		error("COMPILATION FAILED!")

	lines = [l.rstrip() for l in open("compile_log.tmp").readlines()]
	# os.remove("compile_log.tmp")

	functions = dict()
	getFunctions()
	CONTRACT_ADDRESS = getContractAddress()

SIGN = None

def error(msg):
	print "ERROR!", msg
	quit(1)

def exec_and_parse(method, params, expected_ec, options):
	global lines, SIGN
	if "--trace" not in options:
		options = options + " --trace"
	sign = ("--sign " + SIGN) if SIGN else "";
	if method and method not in functions:
		error("Cannot find method '{}'".format(method)) 
	if method == None:
		body = ""
	elif method == "":
		body = "--body 00"
	else:
		id = functions[method]
		body = "--body 00{}{}".format(id, params)
	cmd = "./target/debug/tvm_linker test {} {} {} {} >exec_log.tmp".format(CONTRACT_ADDRESS, body, sign, options)
	# print cmd
	ec = os.system(cmd)
	assert ec == 0, ec

	lines = [l.rstrip() for l in open("exec_log.tmp").readlines()]
	# os.remove("exec_log.tmp")

	ec = getExitCode()
	assert ec == expected_ec, "ec = {}".format(ec)
	
def expect_failure(method, params, expected_ec, options):
	exec_and_parse(method, params, expected_ec, options)
	print("OK:  {} {} {}".format(method, params, expected_ec))
	
def expect_success(method, params, expected, options):
	exec_and_parse(method, params, 0, options)
	stack = getStack()
	if expected != None and stack != expected:
		print("Failed:  {} {}".format(method, params))
		print("EXP: ", expected)
		print("GOT: ", stack)
		quit(1)
	print("OK:  {} {} {}".format(method, params, expected))

def expect_output(regex):
	for l in lines:
		match = re.search(regex, l);
		if match:
			print "> ", match.group(0)
			return
	assert False, regex

	# '''

compile1('test_factorial.code', 'stdlib_sol.tvm')
expect_success('constructor', "", "", "")
expect_success('main', "0003", "6", "")
expect_success('main', "0006", "726", "")

compile1('test_signature.code', 'stdlib_sol.tvm')
expect_failure('constructor', "", 100, "")
SIGN = "key1"
expect_success('constructor', "", "", "")
expect_success('get_role', "", "1", "")
SIGN = None
expect_failure('get_role', "", 100, "")
expect_failure('set_role', "", 9, "")
expect_failure('set_role', "01", 100, "")
SIGN = "key2"
expect_success('get_role', "", "0", "")
expect_success('set_role', "02", "", "")
expect_success('get_role', "", "2", "")

SIGN = None
compile1('test_inbound_int_msg.tvm', None)
expect_success("", "", "-1", "--internal 15000000000")

compile1('test_send_int_msg.tvm', 'stdlib_sol.tvm')
expect_success(None, "", None, "")	# check empty input (deploy)
expect_success('main', "", None, "--internal 0 --decode-c6")
expect_output(r"destination : 0:0+007F")
expect_output(r"CurrencyCollection: Grams.*value = 1000]")

compile1('test_send_int_msg.tvm', 'stdlib_sol.tvm')
expect_success('main', "", None, "--decode-c6")
expect_output(r"destination : 0:0+007F")
expect_output(r"CurrencyCollection: Grams.*value = 1000]")
	
compile1('test_send_msg.code', 'stdlib_sol.tvm')
expect_success(None, "", None, "")	# check empty input (deploy)
expect_success('get_allowance', "1122334455660000000000000000000000000000000000000000005544332211", None, "--internal 0 --decode-c6 --trace")
expect_output(r"destination : 0:1122334455660000000000000000000000000000000000000000005544332211")
expect_output(r"body  : .* data: \[0, 26, 11, 86, 135, 0, 0, 0, 0, 0, 0, 0, 0, ")


compile1('test_msg_sender.code', None)
expect_success(None, "", None, "--internal 0 --trace")	# check empty input (deploy)


compile1('test_msg_sender2.code', 'stdlib_sol.tvm')
# check internal message
expect_success('main', "", "0", "--internal 0")
# check external message
expect_success('main', "", "0", "")

#check msg.value
compile1('test_msg_value.code', 'stdlib_sol.tvm')
expect_success("main", "", "15000000000", "--internal 15000000000")


#check msg.sender
compile1('test_balance.code', 'stdlib_sol.tvm')
expect_success("main", "", "100000000000", "--internal 0")

compile2('contract09-a')
expect_success('sendMoneyAndNumber', ("12" * 32) + ("7" * 16), None, "--internal 0 --decode-c6")
expect_output(r"destination : 0:12121212")
expect_output(r"CurrencyCollection: Grams.*value = 3000000]")
expect_output(r"body.*119, 119, 119, 119, 119, 119, 119, 119, 128\]")

#check tvm_balance
compile1('test_tvm_balance.code', 'stdlib_sol.tvm')
expect_success("main", "", "10000", "--internal 0")

# TODO: cannot predict value of now, need to test it somehow
#check tvm_now
compile1('test_now.code', 'stdlib_sol.tvm')
# expect_success("main", "", "1564090968", "--internal 0")

#check tvm_address
compile1('test_tvm_address.code', 'stdlib_sol.tvm')
expect_success("main", "", "0", "--internal 0")

#check tvm_block_lt
compile1('test_tvm_block_lt.code', 'stdlib_sol.tvm')
expect_success("main", "", "0", "--internal 0")

#check tvm_trans_lt
compile1('test_tvm_trans_lt.code', 'stdlib_sol.tvm')
expect_success("main", "", "0", "--internal 0")

#check tvm_rand_seed
compile1('test_tvm_rand_seed.code', 'stdlib_sol.tvm')
expect_success("main", "", "0", "--internal 0")

#check array length change
compile1('test_array_size.code', 'stdlib_sol.tvm')
expect_success("main", "0000000000000000000000000000000000000000000000000000000000000002", "2", "--internal 0")

cleanup()
