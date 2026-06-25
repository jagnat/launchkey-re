// Walk UP the call graph from LED driver functions to find the render + LED API.
// Decompiles immediate callers. Output -> notes/ghidra-callers.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.io.*;
import java.util.*;

public class FindCallers extends GhidraScript {
    public void run() throws Exception {
        long[] seeds = {0x080097b0L};
        ReferenceManager rm=currentProgram.getReferenceManager();
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        StringBuilder sb=new StringBuilder("# Callers of LED driver functions\n\n");
        Set<Function> toDecomp=new LinkedHashSet<>();
        for(long s:seeds){
            Address ep=toAddr(s);
            Function callee=getFunctionContaining(ep);
            sb.append("## callers of "+(callee!=null?callee.getName():"?")+" @ "+ep+":\n");
            for(Reference r:rm.getReferencesTo(ep)){
                Address from=r.getFromAddress();
                Function cf=getFunctionContaining(from);
                if(cf!=null){
                    sb.append("   <- "+cf.getName()+" @ "+cf.getEntryPoint()
                              +"  ("+cf.getBody().getNumAddresses()+" b)\n");
                    toDecomp.add(cf); // skip known ISR
                }
            }
        }
        sb.append("\n===== DECOMPILATIONS of callers =====\n");
        for(Function f:toDecomp){
            // also list this function's RAM/flash data refs to spot the framebuffer
            TreeSet<Long> ram=new TreeSet<>();
            for(InstructionIterator ii=currentProgram.getListing().getInstructions(f.getBody(),true);ii.hasNext();)
              for(Reference r:ii.next().getReferencesFrom()){long to=r.getToAddress().getOffset();
                if(to>=0x20000000L&&to<0x20010000L) ram.add(to);}
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+"  RAMrefs="+hx(ram)+" ===== */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// fail\n");
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-callers.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath());
    }
    String hx(Collection<Long> c){StringBuilder b=new StringBuilder();for(long v:c)b.append(String.format("0x%08X ",v));return b.toString();}
}
