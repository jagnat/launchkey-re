// Dump all non-default symbols to re/symbols.tsv (canonical, address-sorted) and
// write a coverage metric to re/coverage.txt. Round-trips with ImportSymbols, so
// you can rename in the Ghidra GUI, run this, and commit the diff.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class ExportSymbols extends GhidraScript {
    boolean isDefault(String n) {
        String[] pre = {"FUN_","thunk_FUN_","LAB_","DAT_","UNK_","SUB_","caseD_",
                        "switchD_","u_","s_","PTR_","DACK_","EXT_","__switch"};
        for (String p : pre) if (n.startsWith(p)) return true;
        return false;
    }
    public void run() throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        TreeMap<Long, String[]> rows = new TreeMap<>();
        int total = 0, named = 0; long codeBytes = 0, namedBytes = 0;
        for (FunctionIterator it = fm.getFunctions(true); it.hasNext();) {
            Function fn = it.next();
            total++;
            long sz = fn.getBody().getNumAddresses();
            codeBytes += sz;
            if (!isDefault(fn.getName())) {
                named++; namedBytes += sz;
                rows.put(fn.getEntryPoint().getOffset(), new String[]{"func", fn.getName()});
            }
        }
        SymbolTable st = currentProgram.getSymbolTable();
        for (SymbolIterator si = st.getAllSymbols(false); si.hasNext();) {
            Symbol s = si.next();
            if (s.getSource() == SourceType.USER_DEFINED && s.getSymbolType() == SymbolType.LABEL) {
                long off = s.getAddress().getOffset();
                if (!rows.containsKey(off)) rows.put(off, new String[]{"data", s.getName()});
            }
        }
        StringBuilder sb = new StringBuilder();
        sb.append("# Launchkey Mini MK3 v1.2 (build461) firmware — symbol map / RE checkpoint\n");
        sb.append("# Source of truth for names. Edit here or in Ghidra; ImportSymbols replays this.\n");
        sb.append("# addr\tkind\tname\n");
        for (Map.Entry<Long, String[]> e : rows.entrySet())
            sb.append(String.format("0x%08X\t%s\t%s\n", e.getKey(), e.getValue()[0], e.getValue()[1]));
        try (PrintWriter pw = new PrintWriter("/Users/jagi/Programming/h4/re/symbols.tsv")) { pw.print(sb); }

        double pct = total > 0 ? 100.0 * named / total : 0;
        double bpct = codeBytes > 0 ? 100.0 * namedBytes / codeBytes : 0;
        String cov = String.format(
            "functions named: %d / %d (%.1f%%)\n" +
            "code bytes in named funcs: %d / %d (%.1f%%)\n",
            named, total, pct, namedBytes, codeBytes, bpct);
        try (PrintWriter pw = new PrintWriter("/Users/jagi/Programming/h4/re/coverage.txt")) { pw.print(cov); }
        println(cov);
    }
}
