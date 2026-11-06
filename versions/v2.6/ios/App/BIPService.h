#import <Foundation/Foundation.h>
NS_ASSUME_NONNULL_BEGIN
typedef BOOL (^BIPProgress)(NSInteger,NSString*);
@interface BIPOutput : NSObject
@property(nonatomic,strong,nullable) NSData* carrierPNG;
@property(nonatomic,strong,nullable) NSData* secretData;
@property(nonatomic,copy) NSString* text;
@property(nonatomic,copy) NSString* details;
@property(nonatomic) BOOL png;
@property(nonatomic) unsigned long long seconds;
@end
@interface BIPService : NSObject
+ (NSString*)generateKey;
+ (nullable NSData*)backupKey:(NSString*)password salt:(NSData*)salt error:(NSError**)error;
// Keep this integer-returning API explicit; TextCodec converts NSError to Swift Error.
+ (NSInteger)unitCount:(NSString*)text error:(NSError * _Nullable * _Nullable)error __attribute__((swift_error(none)));
+ (nullable BIPOutput*)encrypt:(NSData*)carrier secret:(nullable NSData*)secret text:(NSString*)text key:(NSString*)key png:(BOOL)png strong:(BOOL)strong progress:(BIPProgress)progress error:(NSError**)error;
+ (nullable BIPOutput*)decrypt:(NSData*)carrier key:(NSString*)key progress:(BIPProgress)progress error:(NSError**)error;
@end
NS_ASSUME_NONNULL_END
