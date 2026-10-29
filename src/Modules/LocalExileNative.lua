-- Windows-only local file picker and one-shot exporter process. No shell or network transport.
local ffi = require("ffi")
local M = { }
if not pcall(ffi.typeof, "EB_STARTUPINFOW") then
	ffi.cdef[[
	typedef struct { unsigned long nLength; void* lpSecurityDescriptor; int bInheritHandle; } EB_SECURITY_ATTRIBUTES;
	typedef struct { unsigned long cb; unsigned short* lpReserved; unsigned short* lpDesktop; unsigned short* lpTitle;
		unsigned long dwX,dwY,dwXSize,dwYSize,dwXCountChars,dwYCountChars,dwFillAttribute,dwFlags;
		unsigned short wShowWindow,cbReserved2; unsigned char* lpReserved2; void* hStdInput; void* hStdOutput; void* hStdError; } EB_STARTUPINFOW;
	typedef struct { void* hProcess; void* hThread; unsigned long dwProcessId,dwThreadId; } EB_PROCESS_INFORMATION;
	typedef struct { unsigned long lStructSize; void* hwndOwner; void* hInstance; const unsigned short* lpstrFilter;
		unsigned short* lpstrCustomFilter; unsigned long nMaxCustFilter,nFilterIndex; unsigned short* lpstrFile;
		unsigned long nMaxFile; unsigned short* lpstrFileTitle; unsigned long nMaxFileTitle; const unsigned short* lpstrInitialDir;
		const unsigned short* lpstrTitle; unsigned long Flags; unsigned short nFileOffset,nFileExtension;
		const unsigned short* lpstrDefExt; intptr_t lCustData; void* lpfnHook; const unsigned short* lpTemplateName;
		void* pvReserved; unsigned long dwReserved,FlagsEx; } EB_OPENFILENAMEW;
	int MultiByteToWideChar(unsigned int,unsigned long,const char*,int,unsigned short*,int);
	void* GetForegroundWindow(void);
	int WideCharToMultiByte(unsigned int,unsigned long,const unsigned short*,int,char*,int,const char*,int*);
	int GetOpenFileNameW(EB_OPENFILENAMEW*); unsigned long CommDlgExtendedError(void);
	int CreatePipe(void**,void**,EB_SECURITY_ATTRIBUTES*,unsigned long);
	int SetHandleInformation(void*,unsigned long,unsigned long); int CloseHandle(void*);
	int CreateProcessW(const unsigned short*,unsigned short*,void*,void*,int,unsigned long,void*,const unsigned short*,EB_STARTUPINFOW*,EB_PROCESS_INFORMATION*);
	int ReadFile(void*,void*,unsigned long,unsigned long*,void*); int WriteFile(void*,const void*,unsigned long,unsigned long*,void*);
	int PeekNamedPipe(void*,void*,unsigned long,unsigned long*,unsigned long*,unsigned long*);
	unsigned long WaitForSingleObject(void*,unsigned long); int GetExitCodeProcess(void*,unsigned long*);
	int TerminateProcess(void*,unsigned int); unsigned long GetLastError(void); unsigned long long GetTickCount64(void); void Sleep(unsigned long);
	]]
end
local kernel, dialogs, user = ffi.load("kernel32"), ffi.load("comdlg32"), ffi.load("user32")
local function wide(value)
	local size = kernel.MultiByteToWideChar(65001, 8, value, #value, nil, 0)
	assert(size > 0, "Invalid UTF-8 path")
	local buffer = ffi.new("unsigned short[?]", size + 1)
	assert(kernel.MultiByteToWideChar(65001, 8, value, #value, buffer, size) == size)
	return buffer
end
local function utf8(value)
	local size = kernel.WideCharToMultiByte(65001, 0, value, -1, nil, 0, nil, nil)
	assert(size > 0, "Invalid Windows path")
	local buffer = ffi.new("char[?]", size)
	kernel.WideCharToMultiByte(65001, 0, value, -1, buffer, size, nil, nil)
	return ffi.string(buffer)
end
function M.PickFile(kind)
	local path = ffi.new("unsigned short[32768]")
	local title = wide(kind == "data" and "Choose item-types.json in the LocalExile data folder" or "Choose the LocalExile save database")
	local filter = wide(kind == "data" and "LocalExile game data\0item-types.json\0All files\0*.*\0\0" or "SQLite save database\0*.db;*.sqlite;*.sqlite3\0All files\0*.*\0\0")
	local options = ffi.new("EB_OPENFILENAMEW")
	options.lStructSize = ffi.sizeof(options); options.lpstrFile = path; options.nMaxFile = 32768
	options.hwndOwner = user.GetForegroundWindow()
	options.lpstrFilter = filter; options.lpstrTitle = title; options.nFilterIndex = 1
	options.Flags = 0x00080000 + 0x00001000 + 0x00000800 + 0x00000008 -- Explorer, existing file/path, preserve cwd.
	if dialogs.GetOpenFileNameW(options) == 0 then
		local errorCode = dialogs.CommDlgExtendedError()
		if errorCode ~= 0 then return nil, "Windows file picker failed (" .. tonumber(errorCode) .. ")." end
		return nil
	end
	return utf8(path)
end

function M.Run(executable, input, timeoutMs)
	if type(executable) ~= "string" or executable:find('[%z"\r\n]') or #input > 12 * 1024 * 1024 then
		return nil, "Invalid exporter path or oversized request."
	end
	local handles = { }
	local function keep(handle) handles[#handles + 1] = handle; return handle end
	local function close(handle)
		for i, h in ipairs(handles) do if h == handle then kernel.CloseHandle(h); table.remove(handles, i); return end end
	end
	local process
	local ok, result = pcall(function()
		local security = ffi.new("EB_SECURITY_ATTRIBUTES")
		security.nLength = ffi.sizeof(security); security.bInheritHandle = 1
		local inRead,inWrite,outRead,outWrite = ffi.new("void*[1]"),ffi.new("void*[1]"),ffi.new("void*[1]"),ffi.new("void*[1]")
		assert(kernel.CreatePipe(inRead,inWrite,security,0) ~= 0, "Cannot create input pipe")
		keep(inRead[0]); keep(inWrite[0])
		assert(kernel.CreatePipe(outRead,outWrite,security,0) ~= 0, "Cannot create output pipe")
		keep(outRead[0]); keep(outWrite[0])
		assert(kernel.SetHandleInformation(inWrite[0],1,0) ~= 0 and kernel.SetHandleInformation(outRead[0],1,0) ~= 0)
		local startup = ffi.new("EB_STARTUPINFOW"); startup.cb=ffi.sizeof(startup); startup.dwFlags=0x100
		startup.hStdInput=inRead[0]; startup.hStdOutput=outWrite[0]; startup.hStdError=outWrite[0]
		local info=ffi.new("EB_PROCESS_INFORMATION")
		local command=wide('"' .. executable .. '"')
		assert(kernel.CreateProcessW(wide(executable),command,nil,nil,1,0x08000000,nil,nil,startup,info) ~= 0,
			"Cannot start the bundled exporter. Build/package evryBuild.Export first (Windows error " .. tonumber(kernel.GetLastError()) .. ").")
		process=keep(info.hProcess); keep(info.hThread); close(inRead[0]); close(outWrite[0])
		local written=ffi.new("unsigned long[1]"); local at=0
		while at < #input do
			local sent = kernel.WriteFile(inWrite[0],input:sub(at+1,at+8192),math.min(8192,#input-at),written,nil)
			assert(sent ~= 0 and written[0]>0, "Exporter stopped reading the request (Windows error " .. tonumber(kernel.GetLastError()) .. ")")
			at=at+tonumber(written[0])
		end
		close(inWrite[0])
		local chunks,length={},0; local buffer=ffi.new("char[8192]"); local available=ffi.new("unsigned long[1]"); local read=ffi.new("unsigned long[1]")
		local deadline=tonumber(kernel.GetTickCount64())+(timeoutMs or 60000)
		while true do
			local peek=kernel.PeekNamedPipe(outRead[0],nil,0,nil,available,nil)
			if peek ~= 0 and available[0]>0 then
				assert(kernel.ReadFile(outRead[0],buffer,math.min(8192,tonumber(available[0])),read,nil) ~= 0, "Cannot read exporter result")
				length=length+tonumber(read[0]); assert(length<=128*1024,"Exporter response exceeds 128 KiB")
				chunks[#chunks+1]=ffi.string(buffer,read[0])
			elseif kernel.WaitForSingleObject(process,0)==0 then break
			elseif tonumber(kernel.GetTickCount64())>deadline then error("Exporter timed out. Refresh the character list before retrying; a completed character is never replaced.")
			else kernel.Sleep(10) end
		end
		return table.concat(chunks)
	end)
	if not ok and process then kernel.TerminateProcess(process,1); kernel.WaitForSingleObject(process,5000) end
	for _, handle in ipairs(handles) do kernel.CloseHandle(handle) end
	if not ok then return nil, tostring(result) end
	return result
end
return M
