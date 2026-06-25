// Find + decompile functions that reference given RAM addresses (the LED color
// framebuffer / plane sources), to walk up toward the session color logic.
// Output -> notes/ghidra-writers.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class FindWriters extends GhidraScript {
    public void run() throws Exception {
        long[] targets = {0x2000DF70L,0x2000DF74L,0x2000DF78L,0x2000DF7CL,
                          0x2000BC4CL,0x2000DF08L};
        Set<Long> tset=new HashSet<>(); for(long t:targets) tset.add(t);
        String[] known={};
        Set<String> knownset=new HashSet<>(Arrays.asList(known));

        Listing listing=currentProgram.getListing();
        Map<Function,Set<Long>> fr=new LinkedHashMap<>();
        for(FunctionIterator it=currentProgram.getFunctionManager().getFunctions(true);it.hasNext();){
            Function f=it.next();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();){
                Instruction in=ii.next();
                for(Reference r:in.getReferencesFrom()){
                    long to=r.getToAddress().getOffset();
                    if(tset.contains(to)) fr.computeIfAbsent(f,k->new TreeSet<Long>()).add(to);
                }
            }
        }
        StringBuilder sb=new StringBuilder("# functions referencing LED color RAM\n\n");
        for(Map.Entry<Function,Set<Long>> e:fr.entrySet()){
            Function f=e.getKey();
            boolean known2=knownset.contains(f.getEntryPoint().toString());
            sb.append(String.format("  %-22s @ %s  %d bytes  refs=%s%s\n",
                f.getName(),f.getEntryPoint(),f.getBody().getNumAddresses(),
                hex(e.getValue()),known2?"  <known>":""));
        }
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        sb.append("\n===== DECOMPILATIONS (unknown referencing fns) =====\n");
        for(Function f:fr.keySet()){
            if(knownset.contains(f.getEntryPoint().toString())) continue;
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+"  refs="+hex(fr.get(f))+" ===== */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// fail\n");
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-writers.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath()+"  fns="+fr.size());
    }
    String hex(Collection<Long> c){StringBuilder b=new StringBuilder();for(long v:c)b.append(String.format("0x%08X ",v));return b.toString();}
}
