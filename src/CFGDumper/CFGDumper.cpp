#include "llvm/CodeGen/MachineBasicBlock.h"
#include "llvm/CodeGen/MachineBranchProbabilityInfo.h"
#include "llvm/CodeGen/MachineDominators.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineFunctionPass.h"
#include "llvm/CodeGen/MachineLoopInfo.h"
#include "llvm/CodeGen/Passes.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/IR/GlobalValue.h"
#include "llvm/InitializePasses.h"
#include "llvm/Pass.h"
#include "llvm/PassRegistry.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/Debug.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Target/RegisterTargetPassConfigCallback.h"
#include <optional>

using namespace llvm;

#define DEBUG_TYPE "cfg-json-dumper"

static unsigned getInstructionCount(const MachineBasicBlock &MBB) {
  unsigned Count = 0;
  for (const MachineInstr &MI : MBB) {
    if (!MI.isDebugInstr())
      Count++;
  }
  return Count;
}

static std::optional<std::string> getCallTarget(const MachineBasicBlock &MBB) {
  bool HasCall = false;
  std::string Target = "";

  for (const MachineInstr &MI : MBB) {
    if (MI.isCall()) {
      HasCall = true;
      for (const MachineOperand &MO : MI.operands()) {
        if (MO.isGlobal()) {
          Target = MO.getGlobal()->getName().str();
          break;
        }
        if (MO.isSymbol()) {
          Target = MO.getSymbolName();
          break;
        }
      }
    }
  }

  if (HasCall)
    return Target;
  return std::nullopt;
}

struct BlockInstrStats {
  unsigned BranchInstrCount = 0;
  unsigned ConditionalBranchCount = 0;
  unsigned UnconditionalBranchCount = 0;
  unsigned LoadCount = 0;
  unsigned StoreCount = 0;
  unsigned PhiCount = 0;
  bool HasReturn = false;
  bool HasIndirectBranch = false;
};

static BlockInstrStats getInstrStats(const MachineBasicBlock &MBB) {
  BlockInstrStats S;
  for (const MachineInstr &MI : MBB) {
    if (MI.isDebugInstr())
      continue;
    if (MI.isBranch()) {
      S.BranchInstrCount++;
      if (MI.isConditionalBranch())
        S.ConditionalBranchCount++;
      if (MI.isUnconditionalBranch())
        S.UnconditionalBranchCount++;
      if (MI.isIndirectBranch())
        S.HasIndirectBranch = true;
    }
    if (MI.mayLoad())
      S.LoadCount++;
    if (MI.mayStore())
      S.StoreCount++;
    if (MI.isPHI())
      S.PhiCount++;
    if (MI.isReturn())
      S.HasReturn = true;
  }
  return S;
}

static std::string getTerminatorKind(const MachineBasicBlock &MBB) {
  auto TI = MBB.getFirstTerminator();
  if (TI == MBB.end())
    return "none";
  const MachineInstr &T = *TI;
  if (T.isReturn())
    return "return";
  if (T.isIndirectBranch())
    return "indirect_branch";
  if (T.isConditionalBranch())
    return "conditional_branch";
  if (T.isUnconditionalBranch())
    return "unconditional_branch";
  if (T.isCall())
    return "call";
  if (T.isBranch())
    return "branch";
  return "other";
}

namespace {

static cl::opt<std::string> CFGOutFile("cfg-out-file",
                                       cl::desc("Output file for CFG JSON"),
                                       cl::init("main.cfg.json"));

static cl::opt<bool> CFGPretty("cfg-pretty",
                               cl::desc("Pretty print the output CFG JSON"),
                               cl::init(false));

class CFGJsonDumper : public MachineFunctionPass {
private:
  json::Array FunctionsJson;

public:
  static char ID;

  CFGJsonDumper() : MachineFunctionPass(ID) {
    initializeMachineBranchProbabilityInfoWrapperPassPass(
        *PassRegistry::getPassRegistry());
    initializeMachineLoopInfoWrapperPassPass(*PassRegistry::getPassRegistry());
    initializeMachineDominatorTreeWrapperPassPass(
        *PassRegistry::getPassRegistry());
  }

  StringRef getPassName() const override { return "CFG JSON Dumper Pass"; }

  void getAnalysisUsage(AnalysisUsage &AU) const override {
    AU.setPreservesAll();
    AU.addRequired<MachineBranchProbabilityInfoWrapperPass>();
    AU.addRequired<MachineLoopInfoWrapperPass>();
    AU.addRequired<MachineDominatorTreeWrapperPass>();
    MachineFunctionPass::getAnalysisUsage(AU);
  }

  bool runOnMachineFunction(MachineFunction &MF) override {
    LLVM_DEBUG(dbgs() << "Running CFGJsonDumper on function: " << MF.getName()
                      << "\n");

    auto &MBPI =
        getAnalysis<MachineBranchProbabilityInfoWrapperPass>().getMBPI();
    auto &MLI = getAnalysis<MachineLoopInfoWrapperPass>().getLI();
    auto &MDT = getAnalysis<MachineDominatorTreeWrapperPass>().getDomTree();

    json::Object FuncJson;
    FuncJson["function_name"] = MF.getName();

    json::Array BlocksJson;
    for (const MachineBasicBlock &MBB : MF) {
      json::Object BlockObj;
      if (MBB.getBBID()) {
        BlockObj["id"] = static_cast<int64_t>(MBB.getBBID()->BaseID);
      } else {
        BlockObj["id"] = static_cast<int64_t>(MBB.getNumber());
      }
      BlockObj["name"] = MBB.getName();
      BlockObj["is_entry"] = (&MBB == &MF.front());

      BlockObj["instr_count"] = getInstructionCount(MBB);
      BlockInstrStats Stats = getInstrStats(MBB);
      BlockObj["branch_instr_count"] = static_cast<int64_t>(Stats.BranchInstrCount);
      BlockObj["conditional_branch_count"] =
          static_cast<int64_t>(Stats.ConditionalBranchCount);
      BlockObj["unconditional_branch_count"] =
          static_cast<int64_t>(Stats.UnconditionalBranchCount);
      BlockObj["load_count"] = static_cast<int64_t>(Stats.LoadCount);
      BlockObj["store_count"] = static_cast<int64_t>(Stats.StoreCount);
      BlockObj["phi_count"] = static_cast<int64_t>(Stats.PhiCount);
      BlockObj["has_return"] = Stats.HasReturn;
      BlockObj["has_indirect_branch"] = Stats.HasIndirectBranch;
      BlockObj["terminator_kind"] = getTerminatorKind(MBB);
      BlockObj["loop_depth"] = static_cast<int64_t>(MLI.getLoopDepth(&MBB));
      if (MachineDomTreeNode *N = MDT.getNode(&MBB)) {
        BlockObj["dom_tree_depth"] = static_cast<int64_t>(N->getLevel());
      } else {
        BlockObj["dom_tree_depth"] = static_cast<int64_t>(0);
      }

      if (auto CallTarget = getCallTarget(MBB)) {
        BlockObj["has_call"] = true;
        if (!CallTarget->empty()) {
          BlockObj["call_target"] = *CallTarget;
        }
      }

      // TODO: Here you can add more block features (e.g. IR2Vec, MIR2Vec
      // embeddings)

      json::Array Successors;
      for (const MachineBasicBlock *Succ : MBB.successors()) {
        json::Object EdgeObj;
        if (Succ->getBBID()) {
          EdgeObj["target_id"] = static_cast<int64_t>(Succ->getBBID()->BaseID);
        } else {
          EdgeObj["target_id"] = static_cast<int64_t>(Succ->getNumber());
        }
        BranchProbability Prob = MBPI.getEdgeProbability(&MBB, Succ);
        EdgeObj["prob"] = Prob.toDouble();
        EdgeObj["is_fallthrough"] = MBB.isLayoutSuccessor(Succ);
        Successors.push_back(std::move(EdgeObj));
      }
      BlockObj["successors"] = std::move(Successors);
      BlocksJson.push_back(std::move(BlockObj));
    }
    FuncJson["blocks"] = std::move(BlocksJson);
    FunctionsJson.push_back(std::move(FuncJson));

    return false;
  }

  bool doFinalization(Module &M) override {
    std::error_code EC;
    raw_fd_ostream OS(CFGOutFile, EC, sys::fs::OF_Text);
    if (!EC) {
      if (CFGPretty) {
        // Pretty print JSON with 2 spaces indent
        OS << llvm::formatv("{0:2}", json::Value(std::move(FunctionsJson)))
           << "\n";
      } else {
        // Compact JSON print
        OS << llvm::formatv("{0}", json::Value(std::move(FunctionsJson)))
           << "\n";
      }
    } else {
      errs() << "CFGJsonDumper: Failed to open file " << CFGOutFile << ": "
             << EC.message() << "\n";
    }
    // Clear array just in case it's run multiple times on different modules
    FunctionsJson.clear();
    return false;
  }
};

} // namespace

char CFGJsonDumper::ID = 0;

static RegisterPass<CFGJsonDumper> X("cfg-json-dump", "Dump CFG JSON", false,
                                     false);

static llvm::RegisterTargetPassConfigCallback
    Y([](const TargetMachine &TM, llvm::legacy::PassManagerBase &PM,
         TargetPassConfig *TPC) {
      TPC->insertPass(&llvm::UnpackMachineBundlesID, new CFGJsonDumper());
    });
