// Decompile a fixed list of functions + list the data addresses each references
// (to locate the LED framebuffer / palette). Output -> notes/ghidra-decomp.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class DecompList extends GhidraScript {
    public void run() throws Exception {
        long[] addrs = {0x0801111eL,0x0800ce3cL,0x0800cef4L,0x08010fe2L};
        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        Listing listing=currentProgram.getListing();
        StringBuilder sb=new StringBuilder();
        for(long a:addrs){
            Address ep=toAddr(a);
            Function f=getFunctionContaining(ep);
            if(f==null){sb.append("\n// no function @ "+ep+"\n");continue;}
            // collect data refs (flash const tables + RAM framebuffer)
            TreeSet<Long> flash=new TreeSet<>(), ram=new TreeSet<>();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();){
                Instruction in=ii.next();
                for(Reference r:in.getReferencesFrom()){
                    long to=r.getToAddress().getOffset();
                    if(to>=0x20000000L&&to<0x20010000L) ram.add(to);
                    else if(to>=0x08008000L&&to<0x08020000L) flash.add(to);
                }
            }
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()+" =====\n");
            sb.append("   RAM refs:   "+hex(ram)+"\n");
            sb.append("   FLASH refs: "+hex(flash)+" */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// decompile failed\n");
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-decomp.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath());
    }
    String hex(Collection<Long> c){StringBuilder b=new StringBuilder();for(long v:c)b.append(String.format("0x%08X ",v));return b.toString();}
}
