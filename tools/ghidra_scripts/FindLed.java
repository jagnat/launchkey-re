// Buckets peripheral xrefs by function, then decompiles SPI/DMA/GPIO-output
// candidates (the likely pad-LED driver). Output -> notes/ghidra-led-analysis.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class FindLed extends GhidraScript {
    static class P { String name; long lo, hi; P(String n,long a,long b){name=n;lo=a;hi=b;} }

    public void run() throws Exception {
        P[] ranges = new P[]{
            new P("SPI1",        0x40013000L,0x400133FFL),
            new P("SPI2",        0x40003800L,0x40003BFFL),
            new P("SPI4",        0x40013400L,0x400137FFL),
            new P("DMA1",        0x40026000L,0x400263FFL),
            new P("DMA2",        0x40026400L,0x400267FFL),
            new P("TIM1",        0x40010000L,0x400103FFL),
            new P("GPIOA",       0x40020000L,0x400203FFL),
            new P("GPIOB",       0x40020400L,0x400207FFL),
            new P("GPIOC",       0x40020800L,0x40020BFFL),
            new P("GPIOD",       0x40020C00L,0x40020FFFL),
            new P("GPIOE",       0x40021000L,0x400213FFL),
            new P("USB_OTG_FS",  0x50000000L,0x5003FFFFL),
            new P("I2C1",        0x40005400L,0x400057FFL),
            new P("ADC1",        0x40012000L,0x400123FFL),
        };
        // peripheral -> set of function entry addrs
        Map<String,Set<Function>> hits = new LinkedHashMap<>();
        for (P p: ranges) hits.put(p.name, new LinkedHashSet<Function>());
        // function -> set of peripherals it touches
        Map<Function,Set<String>> funcPeriph = new LinkedHashMap<>();

        Listing listing = currentProgram.getListing();
        FunctionIterator fit = currentProgram.getFunctionManager().getFunctions(true);
        int nfunc=0;
        while (fit.hasNext()) {
            Function f = fit.next(); nfunc++;
            InstructionIterator ii = listing.getInstructions(f.getBody(), true);
            while (ii.hasNext()) {
                Instruction in = ii.next();
                for (Reference r : in.getReferencesFrom()) {
                    long to = r.getToAddress().getOffset();
                    for (P p: ranges) if (to>=p.lo && to<=p.hi) {
                        hits.get(p.name).add(f);
                        funcPeriph.computeIfAbsent(f,k->new TreeSet<String>()).add(p.name);
                    }
                }
            }
        }

        StringBuilder sb = new StringBuilder();
        sb.append("# Ghidra peripheral xref map  (functions analyzed: "+nfunc+")\n\n");
        sb.append("## peripheral -> #functions touching it\n");
        for (P p: ranges) sb.append(String.format("  %-12s %d\n", p.name, hits.get(p.name).size()));

        // The LED driver most likely touches SPI1 (and maybe DMA2). List those funcs.
        sb.append("\n## functions referencing SPI1 (prime pad-LED driver candidates)\n");
        List<Function> spi1 = new ArrayList<>(hits.get("SPI1"));
        for (Function f: spi1)
            sb.append(String.format("  %-30s @ %s   touches=%s\n",
                f.getName(), f.getEntryPoint(), funcPeriph.get(f)));

        // Decompile SPI1 candidates + any function touching both SPI and DMA.
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        Set<Function> toDecomp = new LinkedHashSet<>(spi1);
        sb.append("\n\n===================== DECOMPILATIONS =====================\n");
        for (Function f: toDecomp) {
            DecompileResults res = dec.decompileFunction(f, 60, monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()
                      +"  (touches "+funcPeriph.get(f)+") ===== */\n");
            if (res!=null && res.decompileCompleted())
                sb.append(res.getDecompiledFunction().getC());
            else
                sb.append("// decompile failed\n");
        }
        dec.dispose();

        File out = new File("/Users/jagi/Programming/h4/notes/ghidra-led-analysis.txt");
        try (PrintWriter pw = new PrintWriter(out)) { pw.print(sb.toString()); }
        println("Wrote "+out.getAbsolutePath());
        println("SPI1 candidate functions: "+spi1.size());
    }
}
