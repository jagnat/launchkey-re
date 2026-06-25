// One-shot export of a queryable corpus so day-to-day investigation needs NO
// Ghidra launch (grep the TSVs / read a slice of firmware.c instead). Produces:
//   re/firmware.c     full decompilation, one block per function
//   re/functions.tsv  addr name size ncallers ncallees cline nclines signature
//   re/xrefs.tsv      from_addr from_name to_addr to_name kind(call|data)
//   re/strings.tsv    addr string
//   re/data.tsv       addr name type len
//   re/symbols.tsv    canonical non-default symbol map (the checkpoint)
//   re/coverage.txt   named/total metric
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class ExportCorpus extends GhidraScript {
    static final String DIR = "/Users/jagi/Programming/h4/re/";

    boolean isDefault(String n) {
        String[] pre = {"FUN_","thunk_FUN_","LAB_","DAT_","UNK_","SUB_","caseD_",
                        "switchD_","u_","s_","PTR_","DACK_","EXT_","__switch"};
        for (String p : pre) if (n.startsWith(p)) return true;
        return false;
    }
    static int countLines(String s) { int n=0; for (int i=0;i<s.length();i++) if (s.charAt(i)=='\n') n++; return n; }

    public void run() throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);

        StringBuilder cFile = new StringBuilder();
        cFile.append("/* Launchkey Mini MK3 v1.2 (build461) — full decompilation.\n");
        cFile.append(" * GENERATED from Ghidra; names come from re/symbols.tsv. Do NOT hand-edit. */\n\n");
        int curLine = countLines(cFile.toString()) + 1;

        List<String> funcRows = new ArrayList<>();
        StringBuilder xrefs = new StringBuilder("# from_addr\tfrom_name\tto_addr\tto_name\tkind\n");
        int total = 0, named = 0; long codeBytes = 0, namedBytes = 0;

        for (FunctionIterator it = fm.getFunctions(true); it.hasNext();) {
            Function fn = it.next();
            total++;
            long sz = fn.getBody().getNumAddresses();
            codeBytes += sz;
            String name = fn.getName();
            boolean isNamed = !isDefault(name);
            if (isNamed) { named++; namedBytes += sz; }

            DecompileResults res = dec.decompileFunction(fn, 60, monitor);
            String sig = (res != null && res.getDecompiledFunction() != null)
                         ? res.getDecompiledFunction().getSignature().trim() : (name + "()");
            String body = (res != null && res.decompileCompleted())
                          ? res.getDecompiledFunction().getC() : "// decompile failed\n";

            String header = "/* ==== " + name + " @ " + fn.getEntryPoint()
                          + "  (" + sz + " b, " + fn.getCallingFunctions(monitor).size()
                          + " callers) ==== */\n";
            String block = header + body + "\n";
            int startLine = curLine;
            cFile.append(block);
            int nclines = countLines(block);
            curLine += nclines;

            int ncallers = fn.getCallingFunctions(monitor).size();
            Set<Function> callees = fn.getCalledFunctions(monitor);
            funcRows.add(String.format("0x%08X\t%s\t%d\t%d\t%d\t%d\t%d\t%s",
                fn.getEntryPoint().getOffset(), name, sz, ncallers, callees.size(),
                startLine, nclines, sig.replace('\t',' ').replace('\n',' ')));

            // call edges
            for (Function ce : callees)
                xrefs.append(String.format("0x%08X\t%s\t0x%08X\t%s\tcall\n",
                    fn.getEntryPoint().getOffset(), name, ce.getEntryPoint().getOffset(), ce.getName()));
            // data refs (loads/stores/pointers from this function's instructions)
            for (InstructionIterator ii = listing.getInstructions(fn.getBody(), true); ii.hasNext();) {
                Instruction insn = ii.next();
                for (Reference r : insn.getReferencesFrom()) {
                    if (!r.getReferenceType().isData()) continue;
                    long to = r.getToAddress().getOffset();
                    Symbol ts = getSymbolAt(r.getToAddress());
                    String tn = ts != null ? ts.getName() : "";
                    xrefs.append(String.format("0x%08X\t%s\t0x%08X\t%s\tdata\n",
                        insn.getAddress().getOffset(), name, to, tn));
                }
            }
        }
        dec.dispose();

        // strings
        StringBuilder strs = new StringBuilder("# addr\tstring\n");
        for (DataIterator di = listing.getDefinedData(true); di.hasNext();) {
            Data d = di.next();
            Object v = d.getValue();
            if (v instanceof String) {
                String s = ((String) v).replace("\n","\\n").replace("\t","\\t");
                strs.append(String.format("0x%08X\t%s\n", d.getAddress().getOffset(), s));
            }
        }

        // labeled data (non-default named data symbols)
        StringBuilder dataTsv = new StringBuilder("# addr\tname\ttype\tlen\n");
        SymbolTable st = currentProgram.getSymbolTable();
        TreeMap<Long,String[]> symRows = new TreeMap<>();
        for (FunctionIterator it = fm.getFunctions(true); it.hasNext();) {
            Function fn = it.next();
            if (!isDefault(fn.getName()))
                symRows.put(fn.getEntryPoint().getOffset(), new String[]{"func", fn.getName()});
        }
        for (SymbolIterator si = st.getAllSymbols(false); si.hasNext();) {
            Symbol s = si.next();
            if (s.getSource() == SourceType.USER_DEFINED && s.getSymbolType() == SymbolType.LABEL) {
                long off = s.getAddress().getOffset();
                // SVD register labels (MMIO range) are regenerated by LoadSvd, not part
                // of the human checkpoint — keep them out of symbols.tsv / data.tsv.
                if (off >= 0x40000000L && off < 0x50040000L) continue;
                if (!symRows.containsKey(off)) symRows.put(off, new String[]{"data", s.getName()});
                Data d = listing.getDataAt(s.getAddress());
                String ty = d != null ? d.getDataType().getName() : "?";
                int len = d != null ? d.getLength() : 0;
                dataTsv.append(String.format("0x%08X\t%s\t%s\t%d\n", off, s.getName(), ty, len));
            }
        }

        // symbols.tsv (canonical checkpoint)
        StringBuilder sym = new StringBuilder();
        sym.append("# Launchkey Mini MK3 v1.2 (build461) firmware — symbol map / RE checkpoint\n");
        sym.append("# Source of truth for names. Edit here or in Ghidra; ImportSymbols replays this.\n");
        sym.append("# addr\tkind\tname\n");
        for (Map.Entry<Long,String[]> e : symRows.entrySet())
            sym.append(String.format("0x%08X\t%s\t%s\n", e.getKey(), e.getValue()[0], e.getValue()[1]));

        // functions.tsv (address-sorted)
        funcRows.sort(Comparator.naturalOrder());
        StringBuilder funcs = new StringBuilder("# addr\tname\tsize\tncallers\tncallees\tcline\tnclines\tsignature\n");
        for (String row : funcRows) funcs.append(row).append('\n');

        write("firmware.c", cFile.toString());
        write("functions.tsv", funcs.toString());
        write("xrefs.tsv", xrefs.toString());
        write("strings.tsv", strs.toString());
        write("data.tsv", dataTsv.toString());
        write("symbols.tsv", sym.toString());
        double pct = total>0?100.0*named/total:0, bpct = codeBytes>0?100.0*namedBytes/codeBytes:0;
        write("coverage.txt", String.format(
            "functions named: %d / %d (%.1f%%)\ncode bytes in named funcs: %d / %d (%.1f%%)\n",
            named, total, pct, namedBytes, codeBytes, bpct));
        println("ExportCorpus: " + total + " functions, " + named + " named (" + String.format("%.1f%%",pct) + ")");
    }
    void write(String fn, String s) throws Exception {
        try (PrintWriter pw = new PrintWriter(DIR + fn)) { pw.print(s); }
    }
}
