// Trace the SPI/LED data path via RAM handle xrefs (HAL handles live in RAM).
// Builds a histogram of referenced RAM addresses in the handle region, then
// decompiles the non-init functions that touch them.
// Output -> notes/ghidra-led-trace.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class FindLed2 extends GhidraScript {
    public void run() throws Exception {
        long RAM_LO = 0x20002000L, RAM_HI = 0x20004000L;   // handle struct region
        String INIT = "080083bc";                          // the big hw init, exclude

        Listing listing = currentProgram.getListing();
        // ramAddr -> set of functions referencing it
        Map<Long,Set<Function>> ramRefs = new TreeMap<>();
        // function -> set of ram addrs it touches in region
        Map<Function,Set<Long>> funcRam = new LinkedHashMap<>();

        FunctionIterator fit = currentProgram.getFunctionManager().getFunctions(true);
        while (fit.hasNext()) {
            Function f = fit.next();
            InstructionIterator ii = listing.getInstructions(f.getBody(), true);
            while (ii.hasNext()) {
                Instruction in = ii.next();
                for (Reference r : in.getReferencesFrom()) {
                    long to = r.getToAddress().getOffset();
                    if (to>=RAM_LO && to<RAM_HI) {
                        ramRefs.computeIfAbsent(to,k->new LinkedHashSet<Function>()).add(f);
                        funcRam.computeIfAbsent(f,k->new TreeSet<Long>()).add(to);
                    }
                }
            }
        }

        StringBuilder sb = new StringBuilder();
        sb.append("# RAM handle-region xref histogram ("+String.format("0x%X..0x%X",RAM_LO,RAM_HI)+")\n");
        sb.append("# (RAM addr : #funcs : function names)\n\n");
        // candidate functions = those touching the region, excluding the giant init
        Set<Function> cands = new LinkedHashSet<>();
        for (Map.Entry<Long,Set<Function>> e : ramRefs.entrySet()) {
            StringBuilder fns = new StringBuilder();
            for (Function f: e.getValue()) {
                fns.append(f.getName()).append(" ");
                if (!f.getEntryPoint().toString().equals(INIT)) cands.add(f);
            }
            sb.append(String.format("  0x%08X : %d : %s\n", e.getKey(), e.getValue().size(), fns));
        }

        sb.append("\n# candidate (non-init) functions touching the handle region: "+cands.size()+"\n");
        for (Function f: cands)
            sb.append(String.format("  %-26s @ %s  body=%d bytes  ram=%s\n",
                f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses(), funcRam.get(f)));

        // Decompile the smaller candidates (likely transmit / render / callback).
        List<Function> ordered = new ArrayList<>(cands);
        ordered.sort(Comparator.comparingLong(a->a.getBody().getNumAddresses()));
        DecompInterface dec = new DecompInterface(); dec.openProgram(currentProgram);
        sb.append("\n\n===================== DECOMPILATIONS (smallest first) =====================\n");
        int n=0;
        for (Function f: ordered) {
            if (n++>=10) break;
            DecompileResults res = dec.decompileFunction(f, 60, monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()
                      +"  ("+f.getBody().getNumAddresses()+" bytes, ram="+funcRam.get(f)+") ===== */\n");
            if (res!=null && res.decompileCompleted())
                sb.append(res.getDecompiledFunction().getC());
            else sb.append("// decompile failed\n");
        }
        dec.dispose();

        File out = new File("/Users/jagi/Programming/h4/notes/ghidra-led-trace.txt");
        try (PrintWriter pw = new PrintWriter(out)) { pw.print(sb.toString()); }
        println("Wrote "+out.getAbsolutePath()+"  candidates="+cands.size());
    }
}
