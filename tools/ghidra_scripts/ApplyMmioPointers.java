// Type each MMIO literal-pool word (from re/peripherals.tsv) as a pointer, so the
// decompiler links it to the SVD register label (LoadSvd) and shows GPIOC_IDR etc.
// Skips any location that is actually an instruction (coincidental value match).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.PointerDataType;
import java.io.*;

public class ApplyMmioPointers extends GhidraScript {
    public void run() throws Exception {
        File f = new File("/Users/jagi/Programming/h4/re/peripherals.tsv");
        int made = 0, skipInsn = 0, fail = 0;
        try (BufferedReader br = new BufferedReader(new FileReader(f))) {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                String[] p = line.split("\\t+");
                if (p.length < 1) continue;
                long addr;
                try { addr = Long.decode(p[0].trim()); } catch (Exception e) { continue; }
                Address a = toAddr(addr);
                if (getInstructionAt(a) != null) { skipInsn++; continue; }
                try {
                    clearListing(a, a.add(3));
                    createData(a, new PointerDataType());
                    made++;
                } catch (Exception e) { fail++; }
            }
        }
        println("ApplyMmioPointers: pointers=" + made + " skipped(insn)=" + skipInsn + " fail=" + fail);
    }
}
