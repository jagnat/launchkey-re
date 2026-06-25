// Find code that reads the velocity-curve LUT array @0x0801A158 (4x128B curves),
// decompile the user fn(s) and their callers (toward the note-velocity path).
// Output -> notes/ghidra-velocity.txt
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;
import java.io.*;
import java.util.*;

public class VelocityCurve extends GhidraScript {
    public void run() throws Exception {
        long VEL=0x0801A158L, VEL_END=0x0801A358L; // 4 curves * 0x80
        Listing listing=currentProgram.getListing();
        ReferenceManager rm=currentProgram.getReferenceManager();

        Set<Function> users=new LinkedHashSet<>();
        for(FunctionIterator it=currentProgram.getFunctionManager().getFunctions(true);it.hasNext();){
            Function f=it.next();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();){
                for(Reference r:ii.next().getReferencesFrom()){
                    long to=r.getToAddress().getOffset();
                    if(to>=VEL && to<VEL_END){ users.add(f); }
                }
            }
        }
        StringBuilder sb=new StringBuilder("# functions reading velocity LUT @0x0801A158..0x0801A358\n");
        for(Function f:users) sb.append("  "+f.getName()+" @ "+f.getEntryPoint()+"  ("+f.getBody().getNumAddresses()+" b)\n");

        Set<Function> callers=new LinkedHashSet<>();
        sb.append("\n# callers of those:\n");
        for(Function f:users){
            for(Reference r:rm.getReferencesTo(f.getEntryPoint())){
                Function cf=getFunctionContaining(r.getFromAddress());
                if(cf!=null){ callers.add(cf); sb.append("  "+cf.getName()+" @ "+cf.getEntryPoint()+" -> "+f.getName()+"\n"); }
            }
        }

        DecompInterface dec=new DecompInterface(); dec.openProgram(currentProgram);
        sb.append("\n===== DECOMPILATIONS (velocity users + callers) =====\n");
        Set<Function> all=new LinkedHashSet<>(); all.addAll(users); all.addAll(callers);
        for(Function f:all){
            TreeSet<Long> ram=new TreeSet<>(), flash=new TreeSet<>();
            for(InstructionIterator ii=listing.getInstructions(f.getBody(),true);ii.hasNext();)
              for(Reference r:ii.next().getReferencesFrom()){long to=r.getToAddress().getOffset();
                if(to>=0x20000000L&&to<0x20010000L) ram.add(to);
                else if(to>=0x08019000L&&to<0x0801B000L) flash.add(to);}
            DecompileResults res=dec.decompileFunction(f,60,monitor);
            sb.append("\n/* ===== "+f.getName()+" @ "+f.getEntryPoint()
                      +"\n   RAMrefs="+hx(ram)+"\n   LUTregionrefs="+hx(flash)+" ===== */\n");
            sb.append(res!=null&&res.decompileCompleted()?res.getDecompiledFunction().getC():"// fail\n");
        }
        dec.dispose();
        File out=new File("/Users/jagi/Programming/h4/notes/ghidra-velocity.txt");
        try(PrintWriter pw=new PrintWriter(out)){pw.print(sb.toString());}
        println("Wrote "+out.getAbsolutePath()+"  users="+users.size()+" callers="+callers.size());
    }
    String hx(Collection<Long> c){StringBuilder b=new StringBuilder();for(long v:c)b.append(String.format("0x%08X ",v));return b.toString();}
}
