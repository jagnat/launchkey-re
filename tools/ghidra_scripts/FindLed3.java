// Name + decompile the functions that drive SPI2 / DMA2 / TIM1 / TIM2 (the LED
// refresh + DMA engine), excluding the big hw-init. Output -> notes/ghidra-led-hw.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class FindLed3 extends GhidraScript {
    static class P { String n; long lo,hi; P(String n,long a,long b){this.n=n;lo=a;hi=b;} }
    public void run() throws Exception {
        P[] ranges = {
            new P("SPI2",0x40003800L,0x40003BFFL),
            new P("DMA2",0x40026400L,0x400267FFL),
            new P("DMA1",0x40026000L,0x400263FFL),
            new P("TIM1",0x40010000L,0x400103FFL),
            new P("TIM2",0x40000000L,0x400003FFL),
        };
        String INIT="080083bc";
        Listing listing=currentProgram.getListing();
        Map<String,Set<Function>> hits=new LinkedHashMap<>();
        for(P p:ranges) hits.put(p.n,new LinkedHashSet<Function>());
        Map<Function,Set<String>> fp=new LinkedHashMap<>();
        for(FunctionIterator it=currentProgram.getFunctionManager().getFunctions(true);it.hasNext();){
            Function f=it.next();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();){
                Instruction in=ii.next();
                for(Reference r:in.getReferencesFrom()){
                    long to=r.getToAddress().getOffset();
                    for(P p:ranges) if(to>=p.lo&&to<=p.hi){hits.get(p.n).add(f);
                        fp.computeIfAbsent(f,k->new TreeSet<String>()).add(p.n);}
                }
            }
        }
        StringBuilder sb=new StringBuilder("# SPI2/DMA/TIM driver functions\n\n");
        Set<Function> decomp=new LinkedHashSet<>();
        for(P p:ranges){
            sb.append("## "+p.n+":\n");
            for(Function f:hits.get(p.n)){
                boolean isInit=f.getEntryPoint().toString().equals(INIT);
                sb.append(String.format("  %-22s @ %s  %d bytes  touches=%s%s\n",
                    f.getName(),f.getEntryPoint(),f.getBody().getNumAddresses(),fp.get(f),isInit?"  <INIT>":""));
                if(!isInit) decomp.add(f);
            }
        }
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        sb.append("\n===================== DECOMPILATIONS (non-init drivers) =====================\n");
        for(Function f:decomp){
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+"  touches="+fp.get(f)+" ===== */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// decompile failed\n");
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-led-hw.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath()+"  drivers="+decomp.size());
    }
}
