import os, sys, re
import datetime, md5
import gviz_api

from django.http import HttpResponse
from django.conf import settings
from django.template import Context, loader
from django.template.loader import render_to_string

verbose = False
GIT_REPO_DIR = "D:\\code\\basekit-animation"
GIT_USE_REMOTE_BRANCH = True
GIT_DIFF_OPTIONS = "-M -C --ignore-space-at-eol"
GIT_DIFF_CACHE_DIR = "D:\\temp\\gitbranchdiff"
GIT_DEFAULT_BASEBRANCH = "basekit/ml"

GIT_BRANCHES = [ 
	"ant15/dl",
	"ant15/rl/2009.08",
	"basekit/ml",
#	"bball12/ml",
	"fifa/ml", 
	"nhl",
#	"ssx",
]

GIT_DIRECTORIES = [
	"ant",
	"antcommonplugins",
	"databuild",
	"extramath",
	"locoantplugins",
	"paplugins",
	"railtracks",
	"sbuantplugins",
	"stateflow"
]

# ------------------- Utility Functions ----------------------------------------------------------------------------------
# safe conversion from string -> int, 0 if fails
def int_safe(n):
    try:
        val = int(n)
    except:
        val = 0
    return val

def die(msg):
    raise Exception(msg)
		
def read_pipe(c, ignore_error=False):
    if verbose:
        sys.stderr.write('Reading pipe: %s\n' % c)

    pipe = os.popen(c, 'rb')
    val = pipe.read()
    if pipe.close() and not ignore_error:
        die('Command failed: %s' % c)

    return val
	
def read_pipe_lines(c):
	if verbose:
		sys.stderr.write('Reading pipe: %s\n' % c)
    
	pipe = os.popen(c, 'rb')
	val = pipe.readlines()
	if pipe.close():
		die('Command failed: %s' % c)

	return val	
	
def git_cmd(cmd):
	os.chdir(GIT_REPO_DIR);
	return read_pipe("git " + cmd, False)
	
def git_cmdMultiline(cmd):
	os.chdir(GIT_REPO_DIR);
	return read_pipe_lines("git " + cmd)

def git_getCommit(branch):
	branchName = branch if not GIT_USE_REMOTE_BRANCH else "origin/" + branch
	return git_cmd("rev-parse %s" % branchName).strip();
	
def git_getShortLog(commit):
	output = git_cmd("log %s --pretty=oneline -n 1" % commit).strip();
	log = re.match(r"\w+(.*)", output).group(1)
	return log[:40]
	
def git_getCommitInfo(commit):
	output = git_cmd("log %s -n 1" % commit).strip();
	return output
	
def get_getCommitTimestamp(commit):
	output = git_cmd("rev-list %s --timestamp -n 1" % commit).strip()
	return int_safe( output.split()[0] );
	
def git_getBranch(commit):
	branchRaw = git_cmd("name-rev --name-only %s" % commit).strip();
	branch = branchRaw
	match = re.match(r"remotes/origin/(.*)", branchRaw)
	if match:
		branch = match.group(1)	
	return branch

def getBranchFilesDifference(branch0Commit, branch1Commit, directory):
	# get file differences
	output = git_cmdMultiline("diff %s --numstat %s %s %s" % (GIT_DIFF_OPTIONS, branch0Commit, branch1Commit, directory));
	fileList=[]
	totalInsertions = 0
	totalDeletions = 0
	for line in output:
		match = re.match(r"(\d+).*?(\d+)\s+(.*)", line);
		insertions = 0
		deletions = 0
		filePath = ""
		if match:
			insertions = int_safe( match.group(1) )
			deletions = int_safe( match.group(2) )	
			filePath = match.group(3)
		fileList.append( {"insertions":insertions, "deletions":deletions, "total":insertions+deletions, "file":filePath} )
		totalInsertions += insertions
		totalDeletions += deletions
		
	diff = { "fileList":fileList, "insertions":totalInsertions, "deletions":totalDeletions, "total":totalInsertions+totalDeletions }
	return diff;

def getBranchLinesDifference(branch0, branch1, directoryRaw):
	# convert branches into commit id's
	branch0Commit = git_getCommit(branch0)
	branch1Commit = git_getCommit(branch1)
	directory = directoryRaw + "/dev"
	return getBranchCommitLinesDifference(branch0Commit, branch1Commit, directory)

def getBranchCommitLinesDifference(commit0, commit1, directory):
	diff = getDiffLinesFromCache(commit0, commit1, directory)

	if not diff:
		# get lines of difference
		output = git_cmd("diff %s --shortstat %s %s %s" % (GIT_DIFF_OPTIONS, commit0, commit1, directory));

		# parse output
		match = re.match(".*?(\d+) files changed.*?(\d+) insertions.*?(\d+) deletions", output);
		insertions = 0
		deletions = 0
		filesChanged = 0
		if match:
			filesChanged = int_safe( match.group(1) )
			insertions = int_safe( match.group(2) )
			deletions = int_safe( match.group(3) )

		diff = {"insertions": insertions, "deletions": deletions, "total":insertions+deletions, "filesChanged": filesChanged, "compareCommit": commit1, "baseCommit": commit0, "directory": directory};
		
		writeDiffLinesToCache( diff )
	return diff;
	
def getDiffHistory(baseCommit, compareCommit, directory):
	commit0List = []
	commit1List = []
	
	commit0Timestamp = get_getCommitTimestamp(baseCommit);
	commit1Timestamp = get_getCommitTimestamp(compareCommit);
	startDate = datetime.date.fromtimestamp( commit0Timestamp if commit0Timestamp > commit1Timestamp else commit1Timestamp )
	date = startDate;
	
	for x in range(30):
		output0 = git_cmd("rev-list %s --first-parent --until=%s --reverse -n 1" % (baseCommit, date.isoformat())).strip();
		if not output0:
			break
		commit0List.append( (output0, date) )
		output1 = git_cmd("rev-list %s --first-parent --until=%s --reverse -n 1" % (compareCommit, date.isoformat())).strip();
		commit1List.append( (output1, date) )
		date -= datetime.timedelta(3)

	diffList = [ ]
	for x in range(len(commit0List)):
		curCommit0 = commit0List[x]
		curCommit1 = commit1List[x]
		diff = getBranchCommitLinesDifference(curCommit0[0], curCommit1[0], directory)
		diffList.append( {'total':diff['total'], 'date':curCommit0[1], 'baseCommit':curCommit0[0], 'compareCommit':curCommit1[0], 'directory':directory } )
		
	return diffList
	
# ------------------- Caching ----------------------------------------------------------------------------------
def initcache(dir = GIT_DIFF_CACHE_DIR):
	if not os.path.exists(dir):
		os.makedirs(dir)
		
def getCacheDirPath( commit0, commit1, directory ):
	key = "%s%s%s" % (commit0, commit1, directory);
	hexKey = md5.new(key).hexdigest()
	fullCacheDir = os.path.join(GIT_DIFF_CACHE_DIR, hexKey[:2]);
	fullCachePath = os.path.join(fullCacheDir, hexKey[2:] + ".cache");
	return fullCacheDir, fullCachePath
		
def getDiffLinesFromCache( commit0, commit1, directory ):	
	cacheDir, cachePath = getCacheDirPath( commit0, commit1, directory )
	
	diff = {}
	if os.path.exists( cachePath ):
		with open( cachePath, 'r' ) as f:
			for line in f.readlines():
				item = line.strip().split(",")
				if "\'int\'" in item[0]:
					value = int_safe( item[2] )
				else:
					value = item[2]				
				diff[item[1]] = value
	return diff
	
def writeDiffLinesToCache( diff ):
	cacheDir, cachePath = getCacheDirPath( diff['baseCommit'], diff['compareCommit'], diff['directory'] )

	initcache( cacheDir )
	with open( cachePath, 'w' ) as f:
		for items in diff.items():
			f.write( "%s,%s,%s\n" % ( str(type(items[1])), items[0], items[1] ) )

	return None
	
def createDiffURL(baseCommit, compareCommit, directory):
	return "?bc=%s&cc=%s&dir=%s" % (baseCommit, compareCommit, directory)
	
# ------------------- Program ----------------------------------------------------------------------------------
def matrix(request):	
	baseBranch = request.GET.get('bb')
	baseBranch = GIT_DEFAULT_BASEBRANCH if not baseBranch else baseBranch

    # Creating the data
	urlcolumns = []
	description = {"branch": ("string", "Branch"), "total": ("number", "Total") }
	for x in range(len(GIT_DIRECTORIES)):
		directory = GIT_DIRECTORIES[x]
		description[directory] = ("number", directory)
		description["url" + str(x)] = ("string", "url")
		urlcolumns.append( "url" + str(x) )
	
	data = []	
	for branch in GIT_BRANCHES:
		row = { "branch": branch }
		total = 0
		for x in range(len(GIT_DIRECTORIES)):
			directory = GIT_DIRECTORIES[x]
			branchDiff = getBranchLinesDifference(baseBranch, branch, directory)			
			row[directory] = branchDiff['total']			
			row["url" + str(x)] = "diff/" + createDiffURL(branchDiff['baseCommit'], branchDiff['compareCommit'], branchDiff['directory'])
			total += branchDiff['total']
		row["total"] = total
		data.append(row)

	# Loading it into gviz_api.DataTable
	data_table = gviz_api.DataTable(description)
	data_table.LoadData(data)
	
	columnHeaders = tuple( ["branch"] + GIT_DIRECTORIES + urlcolumns + ["total"] )

	# Creating a JavaScript code string
	json = data_table.ToJSon(columns_order=columnHeaders, order_by="branch")	
	
	rendered = render_to_string('index.html', { 'json': json,
												'numDirectories': len(GIT_DIRECTORIES),
												'branches': GIT_BRANCHES,
												'baseBranch': baseBranch })
	
	return HttpResponse( rendered )
	
def diff(request):
	baseCommit = request.GET.get('bc')
	compareCommit = request.GET.get('cc')
	directory = request.GET.get('dir')
	
	baseBranch = git_getBranch(baseCommit)
	compareBranch = git_getBranch(compareCommit)
	commitInfo = git_getCommitInfo( compareCommit )
	
	diffHistory = getDiffHistory(baseCommit, compareCommit, directory)
	
	filesDiff = getBranchFilesDifference(baseCommit, compareCommit, directory)
	
	# Loading it into gviz_api.DataTable
	description = {"date": ("date", "Date"),
					"total": ("number", "Lines of Difference"),
					"title0": ("string", "title0"),
					"text0": ("string", "text0"),}	
	data_table = gviz_api.DataTable(description)
	
	data = []
	for diff in diffHistory:
		diffURL = createDiffURL( diff['baseCommit'], diff['compareCommit'], diff['directory'] )
		shortLog = git_getShortLog( diff['compareCommit'] )
		title = "<a href=%s>%s</a>" % (diffURL, shortLog)
		data.append( { 'date': diff['date'], 'total': diff['total'], "title0": title } )
	data_table.LoadData( data )
	
	# Creating a JavaScript code string
	json = data_table.ToJSon(columns_order=("date", "total", "title0", "text0"))		
	
	rendered = render_to_string('diff.html', { 'baseCommit': baseCommit, 
												'compareCommit': compareCommit, 
												'baseBranch': baseBranch,
												'compareBranch': compareBranch,
												'directory': directory,
												'insertions': filesDiff['insertions'],
												'deletions': filesDiff['deletions'],
												'total': filesDiff['total'],
												'fileList': filesDiff['fileList'],
												'commitInfo': commitInfo,
												'diffHistory': diffHistory,
												'json': json })
	
	return HttpResponse( rendered )